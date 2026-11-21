#include "VLHUD.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "VLKing.h"
#include "VLGameMode.h"
#include "VLCommand.h"
#include "GameFramework/PlayerController.h"

namespace
{
	const FLinearColor Ink(0.96f, 0.90f, 0.72f);
	const FLinearColor Gold(0.95f, 0.72f, 0.20f);
	const FLinearColor Green(0.16f, 0.36f, 0.14f);
	const FLinearColor GreenLit(0.24f, 0.50f, 0.20f);
	const FLinearColor Shade(0.03f, 0.05f, 0.03f, 0.72f);
}

FBox2D AVLHUD::ButtonRect(int32 Index, const FVector2D& ViewSize) const
{
	const float S = FMath::Max(ViewSize.Y / 900.f, 0.5f);
	const FVector2D Size(320.f * S, 42.f * S);
	const FVector2D Origin(ViewSize.X * 0.5f - Size.X * 0.5f, ViewSize.Y * 0.23f + Index * 48.f * S);
	return FBox2D(Origin, Origin + Size);
}

int32 AVLHUD::ButtonAt(const FVector2D& Point, const FVector2D& ViewSize) const
{
	for (int32 i = 0; i < NumButtons; ++i)
	{
		if (ButtonRect(i, ViewSize).IsInside(Point))
		{
			return i;
		}
	}
	return -1;
}

AActor* AVLHUD::TrainingBuilding() const
{
	const AVLKing* King = Cast<AVLKing>(GetOwningPawn());
	if (!King || King->IsHeroMode() || bMenu)
	{
		return nullptr;
	}
	AActor* Sel = King->GetSelected();
	return AVLGameMode::TroopFor(Sel).IsEmpty() ? nullptr : Sel;
}

FBox2D AVLHUD::TrainRect(const FVector2D& ViewSize) const
{
	const float S = FMath::Max(ViewSize.Y / 900.f, 0.5f);
	const FVector2D Size(300.f * S, 58.f * S);
	const FVector2D Origin(ViewSize.X - Size.X - 24.f * S, ViewSize.Y - Size.Y - 70.f * S);
	return FBox2D(Origin, Origin + Size);
}

AActor* AVLHUD::SelectedTower() const
{
	const AVLKing* King = Cast<AVLKing>(GetOwningPawn());
	if (!King || King->IsHeroMode() || bMenu)
	{
		return nullptr;
	}
	AActor* Sel = King->GetSelected();
	return UVLCommand::IsTower(Sel) ? Sel : nullptr;
}

int32 AVLHUD::TrainButtonAt(const FVector2D& Point, const FVector2D& ViewSize) const
{
	if (!TrainRect(ViewSize).IsInside(Point))
	{
		return -1;
	}
	if (TrainingBuilding())
	{
		return 0;
	}
	const UVLCommand* Command = UVLCommand::Get(this);
	return (SelectedTower() && Command && Command->TowerCount(SelectedTower()) > 0) ? 0 : -1;
}

FString AVLHUD::MapPath(int32 Map)
{
	static const TCHAR* Paths[NumMaps] = { TEXT("/Game/Maps/L_Town"), TEXT("/Game/Maps/L_Flatlands"), TEXT("/Game/Maps/L_VoxelVillage") };
	return Paths[FMath::Clamp(Map, 0, NumMaps - 1)];
}

const TCHAR* AVLHUD::MapName(int32 Map)
{
	static const TCHAR* Names[NumMaps] = { TEXT("Town"), TEXT("Flatlands"), TEXT("Village") };
	return Names[FMath::Clamp(Map, 0, NumMaps - 1)];
}

int32 AVLHUD::CurrentMap() const
{
	const FString Name = GetWorld() ? GetWorld()->GetMapName() : FString();
	return Name.Contains(TEXT("Flatlands")) ? 1 : (Name.Contains(TEXT("Village")) ? 2 : 0);
}

void AVLHUD::Ring(const FVector& Centre, float Radius, const FLinearColor& Colour, float Thickness)
{
	APlayerController* PC = GetOwningPlayerController();
	if (!PC)
	{
		return;
	}
	const int32 Sides = 20;
	FVector2D Prev;
	bool bPrev = false;
	for (int32 i = 0; i <= Sides; ++i)
	{
		const float A = 2.f * PI * i / Sides;
		FVector2D P;
		const bool bOk = PC->ProjectWorldLocationToScreen(Centre + FVector(FMath::Cos(A), FMath::Sin(A), 0.f) * Radius, P);
		if (bOk && bPrev)
		{
			DrawLine(Prev.X, Prev.Y, P.X, P.Y, Colour, Thickness);
		}
		Prev = P;
		bPrev = bOk;
	}
}

bool AVLHUD::InFlatlands() const
{
	return GetWorld() && GetWorld()->GetMapName().Contains(TEXT("Flatlands"));
}

void AVLHUD::DrawHUD()
{
	Super::DrawHUD();
	if (!Canvas || !GEngine)
	{
		return;
	}
	const FVector2D View(Canvas->ClipX, Canvas->ClipY);
	const float S = FMath::Max(View.Y / 900.f, 0.5f);
	UFont* Font = GEngine->GetLargeFont();

	auto Text = [&](const FString& String, float CentreX, float Y, float Scale, const FLinearColor& Colour)
	{
		float W = 0.f, H = 0.f;
		GetTextSize(String, W, H, Font, Scale);
		DrawText(String, FLinearColor(0.f, 0.f, 0.f, 0.8f), CentreX - W * 0.5f + 2.f, Y + 2.f, Font, Scale);
		DrawText(String, Colour, CentreX - W * 0.5f, Y, Font, Scale);
	};

	if (!bMenu)
	{
		AVLKing* King = Cast<AVLKing>(GetOwningPawn());
		APlayerController* PC = GetOwningPlayerController();
		if (King && PC)
		{
			const bool bHero = King->IsHeroMode();
			if (!bHero)
			{
				AActor* Under = King->PickUnderCursor(PC);
				if (Under && Under != King->GetSelected())
				{
					Brackets(Under, FLinearColor(Ink.R, Ink.G, Ink.B, 0.55f), 2.f * S);
				}
			}
			UVLCommand* Command = UVLCommand::Get(this);
			TArray<AVLKing*> Units;
			if (Command && !bHero)
			{
				Command->GetSelection(Units);
			}
			if (AActor* Sel = King->GetSelected())
			{
				if ((!bHero || Sel != King) && !Units.Contains(Cast<AVLKing>(Sel)))
				{
					Brackets(Sel, Gold, 3.f * S);
				}
			}
			// the crosshair of the mouse-look hero view
			if (King->IsMouseLooking())
			{
				const float CX = View.X * 0.5f, CY = View.Y * King->CrosshairHeight;
				const FLinearColor Cross(1.f, 0.97f, 0.88f, 0.85f);
				DrawRect(Cross, CX - 9.f * S, CY - 1.f * S, 6.f * S, 2.f * S);
				DrawRect(Cross, CX + 3.f * S, CY - 1.f * S, 6.f * S, 2.f * S);
				DrawRect(Cross, CX - 1.f * S, CY - 9.f * S, 2.f * S, 6.f * S);
				DrawRect(Cross, CX - 1.f * S, CY + 3.f * S, 2.f * S, 6.f * S);
			}
			// every selected unit: a gold ring at its feet; where the last orders went: a ring closing on the spot
			for (AVLKing* U : Units)
			{
				Ring(U->GetFeet() + FVector(0.f, 0.f, 6.f), 58.f, Gold, 2.5f * S);
			}
			// their pathways: the route being walked (solid), then the queued points (Shift + right click, dashed),
			// each leg's end a small ring with its number
			{
				APlayerController* OwnPC = GetOwningPlayerController();
				const FLinearColor PathCol(0.55f, 1.f, 0.45f, 0.75f);
				auto Seg = [&](const FVector& A, const FVector& B, bool bDashed)
				{
					FVector2D PA, PB;
					if (!OwnPC->ProjectWorldLocationToScreen(A + FVector(0.f, 0.f, 10.f), PA) || !OwnPC->ProjectWorldLocationToScreen(B + FVector(0.f, 0.f, 10.f), PB))
					{
						return;
					}
					if (!bDashed)
					{
						DrawLine(PA.X, PA.Y, PB.X, PB.Y, PathCol, 2.f * S);
						return;
					}
					const float Len = FVector2D::Distance(PA, PB);
					const int32 N = FMath::Clamp(int32(Len / (14.f * S)), 1, 200);
					for (int32 d = 0; d < N; d += 2)
					{
						const FVector2D P0 = FMath::Lerp(PA, PB, float(d) / N), P1 = FMath::Lerp(PA, PB, float(FMath::Min(d + 1, N)) / N);
						DrawLine(P0.X, P0.Y, P1.X, P1.Y, PathCol, 2.f * S);
					}
				};
				TArray<FVector> Route, Legs;
				for (AVLKing* U : Units)
				{
					U->GetPathway(Route, Legs);
					if (Legs.Num() == 0)
					{
						continue;
					}
					FVector From = U->GetFeet();
					for (const FVector& P : Route)
					{
						Seg(From, P, false);
						From = P;
					}
					for (int32 i = 1; i < Legs.Num(); ++i)
					{
						Seg(Legs[i - 1], Legs[i], true);
					}
					for (int32 i = 0; i < Legs.Num(); ++i)
					{
						Ring(Legs[i] + FVector(0.f, 0.f, 8.f), 26.f, PathCol, 2.f * S);
						FVector2D L;
						if (Legs.Num() > 1 && U == Units[0] && OwnPC->ProjectWorldLocationToScreen(Legs[i] + FVector(0.f, 0.f, 60.f), L))
						{
							DrawText(FString::FromInt(i + 1), PathCol, L.X - 4.f * S, L.Y - 10.f * S, Font, 1.1f * S);
						}
					}
				}
			}
			if (Command && !bHero)
			{
				const double Now = GetWorld()->GetRealTimeSeconds();
				for (const UVLCommand::FMarker& M : Command->GetMarkers())
				{
					const float T = float(Now - M.Time) / UVLCommand::MarkerSeconds;
					if (T >= 0.f && T < 1.f)
					{
						const FLinearColor C(0.45f, 1.f, 0.35f, 1.f - T * 0.6f);
						Ring(M.At + FVector(0.f, 0.f, 8.f), FMath::Lerp(150.f, 35.f, FMath::Sqrt(T)), C, 3.f * S);
						Ring(M.At + FVector(0.f, 0.f, 8.f), 22.f, C, 2.f * S);
					}
				}
				// the box being dragged
				FVector2D A, B;
				if (King->GetSelectionBox(A, B))
				{
					const FVector2D Lo = FVector2D::Min(A, B), Hi = FVector2D::Max(A, B);
					DrawRect(FLinearColor(Gold.R, Gold.G, Gold.B, 0.10f), Lo.X, Lo.Y, Hi.X - Lo.X, Hi.Y - Lo.Y);
					DrawLine(Lo.X, Lo.Y, Hi.X, Lo.Y, Gold, 2.f * S);
					DrawLine(Hi.X, Lo.Y, Hi.X, Hi.Y, Gold, 2.f * S);
					DrawLine(Hi.X, Hi.Y, Lo.X, Hi.Y, Gold, 2.f * S);
					DrawLine(Lo.X, Hi.Y, Lo.X, Lo.Y, Gold, 2.f * S);
				}
				// the platoons, under the mode box
				float Row = 84.f * S;
				for (int32 i = 0; i < UVLCommand::MaxPlatoons; ++i)
				{
					TArray<AVLKing*> Members;
					Command->GetPlatoon(i, Members);
					if (Members.Num() == 0)
					{
						continue;
					}
					const bool bThis = Command->PlatoonOf(Units) == i;
					DrawRect(FLinearColor(0.f, 0.f, 0.f, bThis ? 0.55f : 0.35f), 12.f * S, Row, 330.f * S, 26.f * S);
					DrawText(FString::Printf(TEXT("%d   %s   -   %s"), i + 1, *Command->PlatoonName(i), UVLCommand::FormationName(Command->PlatoonFormation(i))),
						bThis ? Gold : Ink, 22.f * S, Row + 4.f * S, Font, 0.9f * S);
					Row += 30.f * S;
				}
			}
			// the mode and the selection, top left; the controls of this mode along the bottom
			const FString Mode = bHero ? TEXT("HERO") : TEXT("OVERVIEW");
			DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.35f), 12.f * S, 10.f * S, 330.f * S, 64.f * S);
			DrawText(Mode, Gold, 22.f * S, 14.f * S, Font, 1.35f * S);
			FString Info = bHero ? (King->IsArmed() ? King->GetDisplayName() + TEXT("  -  sword drawn") : King->GetDisplayName())
				: (King->GetSelected() ? King->GetSelectedName() : TEXT("nothing selected"));
			if (Units.Num() > 1)
			{
				Info = FString::Printf(TEXT("%d units  -  %s"), Units.Num(), UVLCommand::FormationName(Command->SelectionFormation()));
			}
			else if (Units.Num() == 1)
			{
				Info = Units[0]->GetDisplayName() + (Units[0]->IsGarrisoned() ? TEXT("  -  on the watch tower") : TEXT(""));
			}
			DrawText(Info, Ink, 22.f * S, 44.f * S, Font, 1.0f * S);
			const bool bUnitSelected = Units.Num() > 0;
			const FString Help = bHero
				? (King->IsTroop()
					? (King->IsRanged()
						? TEXT("WASD move   Hold right mouse: draw, let go: shoot   Left click while drawing: lock the draw (right click shoots, left click lets down)   Left click: bash with the bow   Tab overview   Esc menu")
						: TEXT("WASD move   Shift run   Space jump   Tab overview (select the king + Enter to go back to him)   Esc menu"))
					: TEXT("WASD move   Shift run   Space jump   F draw / sheathe   Left click attack   Tab overview   Esc menu"))
				: Command->IsAttackGroundArmed() ? TEXT("ATTACK GROUND: left click where the archers are to shoot   (right click: never mind)")
				: (bUnitSelected
					? TEXT("Right click send them (on the watch tower: archers man it)   Shift+click add   F formation   Ctrl+1..6 platoon   Enter take control   Tab hero")
					: TEXT("WASD pan   Click or drag a box to select   1..6 platoons   Wheel zoom   Q / E turn   Tab hero   Esc menu"));
			// the training panel of a selected barracks / archery range
			if (AActor* B = TrainingBuilding())
			{
				const AVLGameMode* GM = GetWorld()->GetAuthGameMode<AVLGameMode>();
				const FString Kind = AVLGameMode::TroopFor(B);
				const FBox2D R = TrainRect(View);
				const FVector2D Size = R.GetSize();
				float MX = 0.f, MY = 0.f;
				const bool bOver = PC->GetMousePosition(MX, MY) && R.IsInside(FVector2D(MX, MY));
				DrawRect(Gold, R.Min.X - 3.f * S, R.Min.Y - 3.f * S, Size.X + 6.f * S, Size.Y + 6.f * S);
				DrawRect(bOver ? GreenLit : Green, R.Min.X, R.Min.Y, Size.X, Size.Y);
				Text(TEXT("Train ") + Kind, R.Min.X + Size.X * 0.5f, R.Min.Y + 8.f * S, 1.3f * S, Ink);
				const int32 N = GM ? GM->Queued(B) : 0;
				if (N > 0)
				{
					// progress of the one in training, and how many wait
					const float P = GM->Progress(B);
					DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.5f), R.Min.X + 12.f * S, R.Max.Y - 14.f * S, Size.X - 24.f * S, 6.f * S);
					DrawRect(Gold, R.Min.X + 12.f * S, R.Max.Y - 14.f * S, (Size.X - 24.f * S) * P, 6.f * S);
					Text(FString::Printf(TEXT("in training: %d"), N), R.Min.X + Size.X * 0.5f, R.Min.Y - 30.f * S, 0.95f * S, Ink);
				}
			}
			// the watch tower's panel: who mans it, and the button that sends them out
			if (AActor* Tower = SelectedTower())
			{
				const int32 In = Command ? Command->TowerCount(Tower) : 0;
				const FBox2D R = TrainRect(View);
				const FVector2D Size = R.GetSize();
				Text(FString::Printf(TEXT("archers on the lookout: %d of %d"), In, Command ? Command->TowerCapacity(Tower) : 0), R.Min.X + Size.X * 0.5f, R.Min.Y - 30.f * S, 0.95f * S, Ink);
				if (In > 0)
				{
					float MX = 0.f, MY = 0.f;
					const bool bOver = PC->GetMousePosition(MX, MY) && R.IsInside(FVector2D(MX, MY));
					DrawRect(Gold, R.Min.X - 3.f * S, R.Min.Y - 3.f * S, Size.X + 6.f * S, Size.Y + 6.f * S);
					DrawRect(bOver ? GreenLit : Green, R.Min.X, R.Min.Y, Size.X, Size.Y);
					Text(TEXT("Send them out"), R.Min.X + Size.X * 0.5f, R.Min.Y + 14.f * S, 1.3f * S, Ink);
				}
				else
				{
					Text(TEXT("select archers, right click the tower"), R.Min.X + Size.X * 0.5f, R.Min.Y + 14.f * S, 0.95f * S, Ink);
				}
			}
			float W = 0.f, H = 0.f;
			GetTextSize(Help, W, H, Font, 0.95f * S);
			DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.35f), View.X * 0.5f - W * 0.5f - 12.f * S, View.Y - 40.f * S, W + 24.f * S, 30.f * S);
			DrawText(Help, Ink, View.X * 0.5f - W * 0.5f, View.Y - 36.f * S, Font, 0.95f * S);
		}
		return;
	}
	DrawRect(Shade, 0.f, 0.f, View.X, View.Y);
	Text(TEXT("SOVEREIGN REALMS"), View.X * 0.5f, View.Y * 0.17f, 2.6f * S, Gold);
	const int32 Map = CurrentMap();
	static const TCHAR* Blurb[NumMaps] = { TEXT("the island town"), TEXT("flatlands: every building side by side"), TEXT("voxel village") };
	Text(Blurb[Map], View.X * 0.5f, View.Y * 0.17f + 58.f * S, 1.3f * S, Ink);
	const AVLKing* Me = Cast<AVLKing>(GetOwningPawn());
	const FString Angle = FString(TEXT("Camera: ")) + AVLKing::CameraAngleName(Me ? Me->GetCameraAngle() : 0);
	const FString Look = FString::Printf(TEXT("Look speed: %.0f%%"), (Me ? Me->GetLookSpeedSetting() : 0.5f) * 100.f);
	const AVLGameMode* GMode = GetWorld() ? GetWorld()->GetAuthGameMode<AVLGameMode>() : nullptr;
	const FString MusicLabel = FString::Printf(TEXT("Music: %.0f%%"), (GMode ? GMode->GetMusicSetting() : 1.f) * 100.f);
	const FString InvertLabel = FString(TEXT("Invert look: ")) + AVLKing::LookInvertName(Me ? Me->GetLookInvert() : 0);
	const FString Labels[NumButtons] = { TEXT("Resume"), MapName(OtherMap(0)), MapName(OtherMap(1)), MusicLabel, Angle, Look, InvertLabel, TEXT("Quit") };
	for (int32 i = 0; i < NumButtons; ++i)
	{
		const FBox2D R = ButtonRect(i, View);
		const FVector2D Size = R.GetSize();
		DrawRect(Gold, R.Min.X - 3.f * S, R.Min.Y - 3.f * S, Size.X + 6.f * S, Size.Y + 6.f * S);
		DrawRect(Hover == i ? GreenLit : Green, R.Min.X, R.Min.Y, Size.X, Size.Y);
		Text(Labels[i], R.Min.X + Size.X * 0.5f, R.Min.Y + Size.Y * 0.5f - 14.f * S, (i >= NumButtons - 5 && i <= NumButtons - 2 ? 1.1f : 1.5f) * S, Ink);
	}
	const TCHAR* Help[] = {
		TEXT("HERO:   Mouse  look     W A S D  walk     Shift  run     Space  jump     F  draw / sheathe     Left click  attack"),
		TEXT("OVERVIEW:   W A S D  pan     Click / drag a box  select     Right click  send them (double: run, Shift: add a waypoint)     Enter / double click  take control"),
		TEXT("Tab  hero / overview     Wheel  zoom     Q / E or right-drag  turn the view     R  reset     C  postcard view"),
		TEXT("Esc  this menu  (Enter resumes, M map, U music, V camera angle, L look speed, I invert look, X quits)") };
	for (int32 i = 0; i < 4; ++i)
	{
		Text(Help[i], View.X * 0.5f, View.Y * 0.71f + i * 30.f * S, 1.0f * S, Ink);
	}
}

void AVLHUD::Brackets(AActor* Actor, const FLinearColor& Colour, float Thickness)
{
	APlayerController* PC = GetOwningPlayerController();
	if (!Actor || !PC)
	{
		return;
	}
	FVector Origin, Extent;
	Actor->GetActorBounds(true, Origin, Extent);
	if (const AVLKing* King = Cast<AVLKing>(Actor))
	{
		Extent = FVector(45.f, 45.f, 90.f);
		Origin = King->GetActorLocation();
	}
	FVector2D Lo(1e9f, 1e9f), Hi(-1e9f, -1e9f);
	int32 Seen = 0;
	for (int32 i = 0; i < 8; ++i)
	{
		const FVector C = Origin + Extent * FVector((i & 1) ? 1.f : -1.f, (i & 2) ? 1.f : -1.f, (i & 4) ? 1.f : -1.f);
		FVector2D P;
		if (PC->ProjectWorldLocationToScreen(C, P))
		{
			Lo = FVector2D::Min(Lo, P);
			Hi = FVector2D::Max(Hi, P);
			++Seen;
		}
	}
	if (Seen < 2)
	{
		return;
	}
	const float L = FMath::Clamp(FMath::Min(Hi.X - Lo.X, Hi.Y - Lo.Y) * 0.22f, 8.f, 60.f);
	const FVector2D Corners[4] = { Lo, FVector2D(Hi.X, Lo.Y), FVector2D(Lo.X, Hi.Y), Hi };
	for (int32 i = 0; i < 4; ++i)
	{
		const FVector2D C = Corners[i];
		const float SX = (i & 1) ? -1.f : 1.f;
		const float SY = (i & 2) ? -1.f : 1.f;
		DrawLine(C.X, C.Y, C.X + SX * L, C.Y, Colour, Thickness);
		DrawLine(C.X, C.Y, C.X, C.Y + SY * L, Colour, Thickness);
	}
}
