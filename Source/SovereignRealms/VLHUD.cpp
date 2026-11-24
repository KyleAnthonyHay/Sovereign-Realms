// The interface's frame, input, drawing primitives and world-space feedback: the main game's SRHUD.cpp, ported.

#include "VLHUD.h"
#include "VLHUDStyle.h"
#include "SovereignRealms.h"
#include "VLKing.h"
#include "VLGameMode.h"
#include "VLCommand.h"
#include "VLBattle.h"
#include "VLConstruction.h"
#include "VLGrid.h"
#include "VLArcherCombat.h"
#include "VLSwordsmanCombat.h"
#include "VLGraphics.h"
#include "VLFog.h"
#include "AudioDevice.h"
#include "CanvasItem.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "Engine/PostProcessVolume.h"
#include "EngineUtils.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Kismet/KismetSystemLibrary.h"
#include "Misc/App.h"
#include "BatchedElements.h"
#include "CanvasTypes.h"
#include "RenderUtils.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"

using namespace VLStyle;

namespace
{
	// The palette (VLHUDStyle.h) and every colour in the HUD code are written as they should LOOK (sRGB); the canvas
	// wants linear values. The primitives below convert on the way in, so no caller has to think about it.
	FLinearColor Lin(const FLinearColor& C) { return FLinearColor(FMath::Pow(C.R, 2.2f), FMath::Pow(C.G, 2.2f), FMath::Pow(C.B, 2.2f), C.A); }
	// ...and a colour that is already linear (the world-space colours) is taken back out first.
	FLinearColor FromLinear(const FLinearColor& C) { return FLinearColor(FMath::Pow(C.R, 1.f / 2.2f), FMath::Pow(C.G, 1.f / 2.2f), FMath::Pow(C.B, 1.f / 2.2f), C.A); }

	const int32 Caps[5] = { 30, 40, 60, 120, 0 };

	TAutoConsoleVariable<int32> CVarOptHud(TEXT("vl.Opt.Hud"), 1,
		TEXT("1: the HUD looks at the units once a frame, puts the pips' and bars' rectangles into the canvas batch directly, and asks what the pointer is over only when it or the camera moved; 0: as before (to compare)"));
}

float AVLHUD::InterfaceScale = 1.f;

void AVLHUD::BeginPlay()
{
	Super::BeginPlay();
	UIFont = LoadObject<UFont>(nullptr, TEXT("/Engine/EngineFonts/Roboto.Roboto"));
	IconAtlas = LoadObject<UTexture2D>(nullptr, TEXT("/Game/Voxel/UI/T_UI_Icons.T_UI_Icons"));
	TitleArt = LoadObject<UTexture2D>(nullptr, TEXT("/Game/Voxel/UI/T_UI_Title.T_UI_Title"));
	PortraitAtlas = LoadObject<UTexture2D>(nullptr, TEXT("/Game/Voxel/UI/T_UI_Portraits.T_UI_Portraits"));
	UE_LOG(LogSovereignRealms, Log, TEXT("hud: icons %s, title %s, portraits %s"), IconAtlas ? TEXT("loaded") : TEXT("MISSING"), TitleArt ? TEXT("loaded") : TEXT("MISSING"),
		PortraitAtlas ? TEXT("loaded") : TEXT("MISSING"));
	int32 OldMaster = -1;
	if (GConfig)
	{
		float Scale = 1.f;
		if (GConfig->GetFloat(TEXT("SovereignRealms.Interface"), TEXT("Scale"), Scale, GGameUserSettingsIni))
		{
			InterfaceScale = FMath::Clamp(Scale, 0.8f, 1.4f);
		}
		if (!GConfig->GetFloat(TEXT("SovereignRealms.Audio"), TEXT("MasterVolume"), MasterVolume, GGameUserSettingsIni)
			&& GConfig->GetInt(TEXT("SovereignRealms.Audio"), TEXT("Master"), OldMaster, GGameUserSettingsIni))
		{
			MasterVolume = FMath::Clamp(OldMaster, 0, 4) / 4.f;      // (the old setting: 0..4 quarters)
		}
		float Effects = UVLBattle::EffectsVolume;
		if (GConfig->GetFloat(TEXT("SovereignRealms.Audio"), TEXT("Effects"), Effects, GGameUserSettingsIni))
		{
			UVLBattle::EffectsVolume = FMath::Clamp(Effects, 0.f, 1.f);
		}
		int32 OldCap = -1;
		if (!GConfig->GetInt(TEXT("SovereignRealms.Video"), TEXT("FrameCapV2"), FrameCap, GGameUserSettingsIni)
			&& GConfig->GetInt(TEXT("SovereignRealms.Video"), TEXT("FrameCap"), OldCap, GGameUserSettingsIni))
		{
			static const int32 MapOld[4] = { 0, 2, 3, 4 };      // 30->30, 60->60, 120->120, Unlimited->Unlimited
			FrameCap = MapOld[FMath::Clamp(OldCap, 0, 3)];
		}
		GConfig->GetInt(TEXT("SovereignRealms.Game"), TEXT("Difficulty"), PickDifficulty, GGameUserSettingsIni);
		GConfig->GetBool(TEXT("SovereignRealms.Interface"), TEXT("PlatoonsCollapsed"), bPlatoonsCollapsed, GGameUserSettingsIni);
	}
	MasterVolume = FMath::Clamp(MasterVolume, 0.f, 1.f);
	FrameCap = FMath::Clamp(FrameCap, 0, 4);
	PickDifficulty = FMath::Clamp(PickDifficulty, 0, 2);
	PickMap = 1;
	PendingScale = InterfaceScale;
	ApplySettings();
}

void AVLHUD::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (bSettingsDirty)
	{
		SaveSettings();
	}
	Super::EndPlay(EndPlayReason);
}

void AVLHUD::ApplySettings()
{
	if (UWorld* World = GetWorld())
	{
		if (FAudioDeviceHandle Device = World->GetAudioDevice())
		{
			Device->SetTransientPrimaryVolume(MasterVolume);
		}
	}
	UVLGraphics::SetUserFrameCap(Caps[FrameCap]);
	UVLGraphics::Apply(GetWorld());         // quality preset, render scale, dynamic resolution and frame cap
}

void AVLHUD::SaveSettings()
{
	bSettingsDirty = false;
	if (!GConfig)
	{
		return;
	}
	GConfig->SetFloat(TEXT("SovereignRealms.Interface"), TEXT("Scale"), InterfaceScale, GGameUserSettingsIni);
	GConfig->SetFloat(TEXT("SovereignRealms.Audio"), TEXT("MasterVolume"), MasterVolume, GGameUserSettingsIni);
	GConfig->SetFloat(TEXT("SovereignRealms.Audio"), TEXT("Effects"), UVLBattle::EffectsVolume, GGameUserSettingsIni);
	GConfig->SetInt(TEXT("SovereignRealms.Video"), TEXT("FrameCapV2"), FrameCap, GGameUserSettingsIni);
	UVLGraphics::Save();
	GConfig->SetInt(TEXT("SovereignRealms.Game"), TEXT("Difficulty"), PickDifficulty, GGameUserSettingsIni);
	GConfig->SetBool(TEXT("SovereignRealms.Interface"), TEXT("PlatoonsCollapsed"), bPlatoonsCollapsed, GGameUserSettingsIni);
	GConfig->Flush(false, GGameUserSettingsIni);
}

// ------------------------------------------------------------------------------------------------ maps

FString AVLHUD::MapPath(int32 Map)
{
	// (4, the Test World, is Realm v2 opened with ?TestWorld=1: OpenMatch)
	static const TCHAR* Paths[NumMaps] = { TEXT("/Game/Maps/L_RealmV2"), TEXT("/Game/Maps/L_Realm"), TEXT("/Game/Maps/L_Flatlands"), TEXT("/Game/Maps/L_Highlands"), TEXT("/Game/Maps/L_RealmV2"), TEXT("/Game/Maps/L_RealmV3") };
	return Paths[FMath::Clamp(Map, 0, NumMaps - 1)];
}

const TCHAR* AVLHUD::MapName(int32 Map)
{
	static const TCHAR* Names[NumMaps] = { TEXT("Realm v2"), TEXT("Realm"), TEXT("Flatlands"), TEXT("Highlands"), TEXT("Test World"), TEXT("Realm v3") };
	return Names[FMath::Clamp(Map, 0, NumMaps - 1)];
}

int32 AVLHUD::CurrentMap() const
{
	const FString Name = GetWorld() ? GetWorld()->GetMapName() : FString();
	if (const AVLGameMode* Mode = GetWorld() ? GetWorld()->GetAuthGameMode<AVLGameMode>() : nullptr; Mode && Mode->IsTestWorld())
	{
		return 4;                   // the Test World (Realm v2 with both sides at their most)
	}
	// ("L_RealmV2" and "L_RealmV3" contain "Realm": they are asked first)
	return Name.Contains(TEXT("RealmV3")) ? 5 : Name.Contains(TEXT("RealmV2")) ? 0 : (Name.Contains(TEXT("Highlands")) ? 3 : (Name.Contains(TEXT("Flatlands")) ? 2 : 1));
}

bool AVLHUD::InFlatlands() const
{
	return GetWorld() && GetWorld()->GetMapName().Contains(TEXT("Flatlands"));
}

void AVLHUD::OpenMatch(const UObject* WorldContext, int32 Map, int32 Difficulty)
{
	UGameplayStatics::SetGamePaused(WorldContext, false);
	UGameplayStatics::OpenLevel(WorldContext, FName(*MapPath(Map)), true, FString::Printf(TEXT("Match=1?Difficulty=%d%s"), FMath::Clamp(Difficulty, 0, 2), Map == 4 ? TEXT("?TestWorld=1") : TEXT("")));
}

// ------------------------------------------------------------------------------------------------ screens

EVLScreen AVLHUD::GetScreen() const
{
	return Sub != EVLScreen::None ? Sub : Base;
}

void AVLHUD::SetScreen(EVLScreen InScreen)
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	const EVLScreen OldBase = Base;
	if (Sub == EVLScreen::Settings && bSettingsDirty)
	{
		SaveSettings();
	}
	bConfirm = false;
	SaveAsk = INDEX_NONE;
	if (IsSubScreen(InScreen))
	{
		// a sub-screen: over the pause menu in a match, else over the title screen
		if (Base == EVLScreen::None || Base == EVLScreen::End)
		{
			Base = (Battle && Battle->IsPlaying()) ? EVLScreen::Pause : EVLScreen::Main;
		}
		Sub = InScreen;
		if (InScreen == EVLScreen::NewGame)
		{
			PickMap = Base == EVLScreen::Main ? 1 : CurrentMap();
		}
		if (InScreen == EVLScreen::Settings)
		{
			PendingScale = InterfaceScale;
		}
	}
	else
	{
		Base = InScreen;
		Sub = EVLScreen::None;
	}
	if (Base != OldBase)
	{
		// every state starts on its own first screen
		StateTime = GetWorld() ? GetWorld()->GetRealTimeSeconds() : 0.0;
		bLegend = false;
	}
	bMenu = Base != EVLScreen::None;
	UVLGraphics::SetMenuThrottle(GetWorld(), bMenu);
	Press.bPending = false;
	// the pause menu (and what opens from it) pauses the match: troops, buildings, the commander, the clock
	const bool bPause = Base != EVLScreen::None && Base != EVLScreen::End && Battle && Battle->IsPlaying();
	if (UGameplayStatics::IsGamePaused(this) != bPause)
	{
		UGameplayStatics::SetGamePaused(this, bPause);
	}
}

void AVLHUD::OpenSub(EVLScreen NewSub)
{
	if (Sub == EVLScreen::Settings && bSettingsDirty)
	{
		SaveSettings();         // leaving Settings: keep what was changed
	}
	bConfirm = false;
	SaveAsk = INDEX_NONE;
	if (NewSub == EVLScreen::None)
	{
		Sub = EVLScreen::None;
		return;
	}
	SetScreen(NewSub);
}

void AVLHUD::AskConfirm(EConfirm What)
{
	Confirm = What;
	bConfirm = true;
}

void AVLHUD::DoConfirmed()
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	bConfirm = false;
	switch (Confirm)
	{
	case EConfirm::Restart:
		OpenMatch(this, CurrentMap(), Battle ? Battle->GetDifficulty() : PickDifficulty);
		break;
	case EConfirm::MainMenu:
		UGameplayStatics::SetGamePaused(this, false);
		UGameplayStatics::OpenLevel(this, FName(*MapPath(CurrentMap())));      // (no match: the title screen comes up)
		break;
	default:
		UKismetSystemLibrary::QuitGame(this, GetOwningPlayerController(), EQuitPreference::Quit, false);
		break;
	}
}

void AVLHUD::OnEscape()
{
	if (UVLGraphics::DisplayConfirmSeconds() > 0.f)
	{
		UVLGraphics::RevertDisplay();        // ("Keep this display mode?": no)
		return;
	}
	if (bLegend)
	{
		bLegend = false;
		return;
	}
	if (Base == EVLScreen::None && (ChipList != 0 || bAssignOpen))
	{
		ChipList = 0;               // (the Builders' / Spy's list, the Assign picker: put away first)
		bAssignOpen = false;
		return;
	}
	if (Base == EVLScreen::None)
	{
		// while playing: first a building being placed (then the build menu), an armed click (attack ground,
		// attack-move, patrol, guard), then the pause menu
		if (UVLConstruction* Construction = UVLConstruction::Get(this); Construction && Construction->OnEscape())
		{
			return;
		}
		if (UVLCommand* Command = UVLCommand::Get(this); Command && Command->GetArmed() != EVLArm::None)
		{
			Command->Arm(EVLArm::None);
			return;
		}
		// then the selected Builders' queued orders (the job each is on goes on)
		if (UVLCommand* Command = UVLCommand::Get(this))
		{
			TArray<AVLKing*> Units;
			Command->GetSelection(Units);
			if (UVLConstruction* Construction = UVLConstruction::Get(this); Construction && Construction->ClearQueues(Units))
			{
				if (UVLBattle* Battle = UVLBattle::Get(this))
				{
					Battle->PushAlert(TEXT("The Builders' queued orders are cleared"));
					Battle->Play2D(TEXT("S_UIClick"), 0.4f);
				}
				return;
			}
			// the hero view: the selection is let go first (then the pause menu)
			Units.Remove(King);
			if (King && King->IsHeroMode() && Units.Num() > 0)
			{
				Command->ClearSelection();
				if (UVLBattle* Battle = UVLBattle::Get(this))
				{
					Battle->Play2D(TEXT("S_UIClick"), 0.4f);
				}
				UE_LOG(LogSovereignRealms, Log, TEXT("hud: Esc lets the selection go (hero view)"));
				return;
			}
		}
		SetScreen(EVLScreen::Pause);
		return;
	}
	if (bConfirm)
	{
		bConfirm = false;
		return;
	}
	if (SaveAsk != INDEX_NONE)
	{
		SaveAsk = INDEX_NONE;       // (the question over a slot: no)
		return;
	}
	if (Sub != EVLScreen::None)
	{
		OpenSub(EVLScreen::None);
		return;
	}
	if (Base == EVLScreen::Pause)
	{
		SetScreen(EVLScreen::None);
	}
	// the title screen and the end screen stay until a button is chosen
}

void AVLHUD::ToggleLegend()
{
	if (Base == EVLScreen::None)
	{
		bLegend = !bLegend;
	}
	else if (Base != EVLScreen::End)
	{
		OpenSub(Sub == EVLScreen::Controls ? EVLScreen::None : EVLScreen::Controls);
	}
}

void AVLHUD::MenuInput(APlayerController* PC, AVLKing* Me)
{
	float MX = 0.f, MY = 0.f;
	if (PC->WasInputKeyJustPressed(EKeys::LeftMouseButton) && PC->GetMousePosition(MX, MY))
	{
		OnMousePress(FVector2D(MX, MY), false);
	}
	auto Key = [PC](const FKey& K) { return PC->WasInputKeyJustPressed(K); };
	if (UVLGraphics::DisplayConfirmSeconds() > 0.f)
	{
		// "Keep this display mode?": Enter keeps it (Esc goes back: OnEscape); no other key of the menus meanwhile
		if (Key(EKeys::Enter)) { Click(); UVLGraphics::ConfirmDisplay(); }
		return;
	}
	if (Key(EKeys::Enter))
	{
		const UVLBattle* Battle = UVLBattle::Get(this);
		Click();
		if (bConfirm) { DoConfirmed(); }
		else if (Sub == EVLScreen::SaveGame || Sub == EVLScreen::LoadGame) { /* (a slot is picked with the pointer) */ }
		else if (Sub == EVLScreen::NewGame) { SaveSettings(); OpenMatch(this, PickMap, PickDifficulty); }
		else if (Sub != EVLScreen::None) { OpenSub(EVLScreen::None); }
		else if (Base == EVLScreen::Main) { OpenSub(EVLScreen::NewGame); }
		else if (Base == EVLScreen::Pause) { SetScreen(EVLScreen::None); }
		else if (Base == EVLScreen::End) { OpenMatch(this, CurrentMap(), Battle ? Battle->GetDifficulty() : PickDifficulty); }
		return;
	}
	// the keys of the old Esc menu: M the next map, U music, V camera angle, L look speed, I invert, X quits
	if (Base == EVLScreen::Pause || Sub == EVLScreen::Settings)
	{
		AVLGameMode* GM = GetWorld()->GetAuthGameMode<AVLGameMode>();
		if (Key(EKeys::M) && Base == EVLScreen::Pause && Sub == EVLScreen::None)
		{
			const UVLBattle* Battle = UVLBattle::Get(this);
			OpenMatch(this, OtherMap(0), Battle ? Battle->GetDifficulty() : PickDifficulty);
		}
		else if (Key(EKeys::U) && GM) { Click(); GM->CycleMusicVolume(); }
		else if (Key(EKeys::V) && Me) { Click(); Me->CycleCameraAngle(); }
		else if (Key(EKeys::L) && Me) { Click(); Me->CycleLookSpeed(); }
		else if (Key(EKeys::I) && Me) { Click(); Me->CycleLookInvert(); }
		else if (Key(EKeys::X)) { UKismetSystemLibrary::QuitGame(this, PC, EQuitPreference::Quit, false); }
	}
}

// ------------------------------------------------------------------------------------------------ input

bool AVLHUD::IsOverUI(const FVector2D& ViewportPixels) const
{
	if (bMenu || bLegend)
	{
		return true;
	}
	const FVector2D P = ViewportPixels * ToCanvas;
	for (const FBox2D& Box : Blockers)
	{
		if (Box.IsInside(P))
		{
			return true;
		}
	}
	return false;
}

bool AVLHUD::OnMousePress(const FVector2D& ViewportPixels, bool bRight)
{
	if (!IsOverUI(ViewportPixels))
	{
		return false;
	}
	Press.bPending = true;
	Press.bRight = bRight;
	Press.Pos = ViewportPixels * ToCanvas;
	return true;
}

void AVLHUD::LogButtons() const
{
	for (const TPair<uint32, FBox2D>& B : ButtonsLast)
	{
		const FVector2D C = B.Value.GetCenter();
		UE_LOG(LogSovereignRealms, Log, TEXT("hud button %u at %.3f %.3f (%.0f x %.0f px)"), B.Key, C.X / FMath::Max(View.X, 1.f), C.Y / FMath::Max(View.Y, 1.f),
			B.Value.GetSize().X, B.Value.GetSize().Y);
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("hud: screen %d (base %d, sub %d)%s%s, %d panels"), int32(GetScreen()), int32(Base), int32(Sub), bConfirm ? TEXT(", confirm") : TEXT(""),
		bLegend ? TEXT(", controls overlay") : TEXT(""), Blockers.Num());
	UE_LOG(LogSovereignRealms, Log, TEXT("hud: %s; route lines %s: %d segment(s), %d Builder chain(s), %d number(s)%s; mode box shows %s"), King && King->IsHeroMode() ? TEXT("hero view") : TEXT("overview"),
		LineStats.bHidden ? TEXT("hidden (hero view)") : TEXT("shown"), LineStats.Segments, LineStats.Chains, LineStats.Badges, LineStats.bPreview ? TEXT(", the Shift preview to the ghost") : TEXT(""),
		ModeBoxUnit.IsEmpty() ? TEXT("-") : *ModeBoxUnit);
	UE_LOG(LogSovereignRealms, Log, TEXT("hud: troops' order chains drawn: %d, %d number(s); pathways drawn: %d (%d of them one line for a group)"), LineStats.OrderChains, LineStats.OrderBadges, LineStats.Pathways, LineStats.Grouped);
	UE_LOG(LogSovereignRealms, Log, TEXT("hud: tooltips %s; Builders' / Spy's list %d; Assign picker %s; minimap %s, platoon panel %s"), AltHeld() ? TEXT("shown (Option held)") : TEXT("hidden (Option not held)"), ChipList,
		bAssignOpen ? TEXT("open") : TEXT("closed"), MapRect.bIsValid ? TEXT("drawn") : TEXT("not drawn"), PlatoonRect.bIsValid ? TEXT("drawn") : TEXT("not drawn"));
	if (MapRect.bIsValid)
	{
		const FVector2D V(FMath::Max(View.X, 1.f), FMath::Max(View.Y, 1.f));
		UE_LOG(LogSovereignRealms, Log, TEXT("hud: minimap at %.4f %.4f .. %.4f %.4f, world %.0f %.0f .. %.0f %.0f, up yaw %.0f; view box middle at %.4f %.4f, the player's castle at %.4f %.4f"),
			MapRect.Min.X / V.X, MapRect.Min.Y / V.Y, MapRect.Max.X / V.X, MapRect.Max.Y / V.Y, MapWorld.Min.X, MapWorld.Min.Y, MapWorld.Max.X, MapWorld.Max.Y, MapYaw,
			MapViewMid.X / V.X, MapViewMid.Y / V.Y, MapCastleAt.X / V.X, MapCastleAt.Y / V.Y);
	}
}

void AVLHUD::Click(bool bError)
{
	if (UVLBattle* Battle = UVLBattle::Get(this))
	{
		Battle->Play2D(bError ? TEXT("S_UIError") : TEXT("S_UIClick"), bError ? 0.5f : 0.4f);
	}
}

AVLHUD::FBtn AVLHUD::Button(const FBox2D& Box, uint32 Id, bool bEnabled)
{
	FBtn B;
	ButtonsNow.Add({ Id, Box });
	B.bHover = bInputOpen && bMouse && Box.IsInside(Mouse);
	if (bInputOpen && Press.bPending && Box.IsInside(Press.Pos))
	{
		Press.bPending = false;
		if (Press.bRight) { B.bRightClicked = bEnabled; }
		else if (bEnabled) { B.bClicked = true; ActiveId = Id; }
		else { Click(true); }
		UE_LOG(LogSovereignRealms, Log, TEXT("hud: %s on button %u%s"), Press.bRight ? TEXT("right click") : TEXT("click"), Id, bEnabled ? TEXT("") : TEXT(" (disabled)"));
	}
	B.bHeld = ActiveId == Id && bMouseDown;
	// eased hover: 100 ms in and out
	float& H = Hover.FindOrAdd(Id);
	H = FMath::FInterpConstantTo(H, B.bHover && bEnabled ? 1.f : 0.f, Dt, 10.f);
	B.Hot = H;
	return B;
}

// ------------------------------------------------------------------------------------------------ the frame

void AVLHUD::BeginFrame()
{
	PCtrl = GetOwningPlayerController();
	King = Cast<AVLKing>(GetOwningPawn());
	View = FVector2D(Canvas->SizeX, Canvas->SizeY);
	DpiScale = Canvas->Canvas ? FMath::Max(Canvas->Canvas->GetDPIScale(), 0.1f) : 1.f;
	int32 ViewX = 0, ViewY = 0;
	if (PCtrl)
	{
		PCtrl->GetViewportSize(ViewX, ViewY);
	}
	ToCanvas = ViewX > 0 ? View.X / ViewX : 1.f;

	// Design units are pixels at 1080p. Never below 0.8 (a 720p window keeps readable text), and never so large that
	// the bottom row (minimap, selection panel, platoons) no longer fits side by side.
	UI = FMath::Max(View.Y / 1080.f, 0.8f) * FMath::Clamp(InterfaceScale, 0.8f, 1.4f);
	UI = FMath::Max(FMath::Min(UI, View.X / 1500.f), 0.5f);

	Dt = FMath::Min(float(FApp::GetDeltaTime()), 0.1f);
	Now = GetWorld()->GetRealTimeSeconds();
	float MX = 0.f, MY = 0.f;
	bMouse = PCtrl && !(King && King->IsMouseLooking()) && PCtrl->GetMousePosition(MX, MY);
	Mouse = FVector2D(MX, MY) * ToCanvas;
	bMouseDown = PCtrl && PCtrl->IsInputKeyDown(EKeys::LeftMouseButton);
	BlockersNow.Reset();
	ButtonsNow.Reset();
	bTooltip = false;
	bInputOpen = true;
}

float AVLHUD::FitScale(float DesignW, float DesignH) const
{
	return FMath::Min3(1.f, (float(View.X) - PanelLeft - 2.f * U(10.f)) / FMath::Max(DesignW * UI, 1.f), (float(View.Y) - 2.f * U(8.f)) / FMath::Max(DesignH * UI, 1.f));
}

float AVLHUD::PanelX(float CentreX, float W) const
{
	const float Left = PanelLeft + U(10.f);
	return FMath::RoundToFloat(FMath::Clamp(CentreX - W * 0.5f, Left, FMath::Max(Left, float(View.X) - W - U(10.f))));
}

void AVLHUD::EndFrame()
{
	DrawTooltip();
	Press.bPending = false;                  // a press nothing answered is simply spent
	if (!bMouseDown)
	{
		ActiveId = 0;
	}
	Blockers = BlockersNow;
	ButtonsLast = ButtonsNow;
}

void AVLHUD::DrawHUD()
{
	Super::DrawHUD();
	if (!Canvas || !GEngine)
	{
		return;
	}
	BeginFrame();

	UVLBattle* Battle = UVLBattle::Get(this);
	// the title screen when the game comes up without a match to start (the boot, Main menu); it goes when one starts
	if (!bBooted)
	{
		bBooted = true;
		const AVLGameMode* GM = GetWorld()->GetAuthGameMode<AVLGameMode>();
		if (GM && !GM->HasMatchOption() && Battle && !Battle->IsPlaying() && Base == EVLScreen::None)
		{
			SetScreen(EVLScreen::Main);
		}
	}
	if (Battle && Battle->IsPlaying() && Base == EVLScreen::Main)
	{
		SetScreen(EVLScreen::None);
	}
	if (Battle && Battle->GetEndTime() >= VLRules::EndScreenDelay && !bEndShown)
	{
		bEndShown = true;
		SetScreen(EVLScreen::End);
	}

	UpdateTitleBackdrop();
	SaveKeys();                 // F5 the quicksave, F9 loads it

	if (Base != EVLScreen::Main)
	{
		// the match's own interface; under a menu it is still drawn but takes no input
		bInputOpen = Base == EVLScreen::None && !bLegend;
		{
			FVLOptTiming::FScope Timing(FVLOptTiming::HudWorld);
			DrawUnitRings();
			DrawFarPips();
			DrawHealthBars();
		}
		DrawPlatoonTags();
		DrawGuardMarks();
		DrawUnitHighlight();
		DrawTrainingBars();
		DrawBuildFeedback();
		DrawRangeCircles();
		DrawRouteLines();
		DrawOrderChains();
		DrawOrderMarkers();
		DrawPayoutPopups();
		DrawSelectionBox();
		DrawGameHUD();
		bInputOpen = true;
	}
	switch (Base)
	{
	case EVLScreen::Main: DrawMainMenu(); break;
	case EVLScreen::Pause: DrawPauseMenu(); break;
	case EVLScreen::End: DrawEndScreen(); break;
	default: if (bLegend) { DrawLegendOverlay(); } break;
	}
	if (UVLGraphics::DisplayConfirmSeconds() > 0.f)
	{
		DrawDisplayConfirm();       // (an exclusive full screen mode waits to be kept: over everything)
	}
	EndFrame();
	// the hero chip's double click: King David's hero view (as Enter with him selected), after the frame's drawing
	if (AVLKing* Hero = PendingHeroView.Get())
	{
		PendingHeroView = nullptr;
		if (King && Hero->IsAlive())
		{
			King->TakeControlOf(Hero);
			UE_LOG(LogSovereignRealms, Log, TEXT("hud: top bar King David double-clicked: his hero view"));
		}
	}
}

void AVLHUD::UpdateTitleBackdrop()
{
	const bool bTitle = Base == EVLScreen::Main;
	if (King)
	{
		if (bTitle)
		{
			// a wide sweep over the whole map, framed from the ground the level has (any size of map), circling its
			// middle; past the overview's zoom limits
			UVLGrid* Grid = UVLGrid::Get(this);
			if (Grid && !Grid->IsBuilt())
			{
				Grid->EnsureBuilt();
			}
			const FBox2D Ground = (Grid && Grid->IsBuilt()) ? Grid->GetBounds() : FBox2D(FVector2D(-10400.f, -10400.f), FVector2D(10400.f, 10400.f));
			const float Size = FMath::Max(Ground.GetSize().X, Ground.GetSize().Y);
			const FVector2D C = Ground.GetCenter();
			King->SetTitleShot(FVector(C.X, C.Y, GroundZ(C, 0.f)), Size * 1.6f, -38.f);      // (the overview's 30 degree view: about the whole map across)
		}
		else if (King->HasTitleShot())
		{
			King->SetTitleShot(FVector::ZeroVector, 0.f, 0.f);
		}
	}
	// no see-through outlines of units behind the title screen (for the look of it); back when the match starts
	if (bTitle == bSilhouettesOff)
	{
		return;
	}
	bSilhouettesOff = bTitle;
	if (bTitle)
	{
		MutedSilhouettes.Reset();
		for (TActorIterator<APostProcessVolume> It(GetWorld()); It; ++It)
		{
			TArray<FWeightedBlendable>& Blends = It->Settings.WeightedBlendables.Array;
			for (int32 i = 0; i < Blends.Num(); ++i)
			{
				if (Blends[i].Object && Blends[i].Object->GetName().Contains(TEXT("Silhouette")) && Blends[i].Weight > 0.f)
				{
					MutedSilhouettes.Add({ *It, i, Blends[i].Weight });
					Blends[i].Weight = 0.f;
				}
			}
		}
		UE_LOG(LogSovereignRealms, Log, TEXT("title: silhouettes off (%d blendable(s))"), MutedSilhouettes.Num());
	}
	else
	{
		for (const FMutedBlendable& M : MutedSilhouettes)
		{
			if (APostProcessVolume* V = M.Volume.Get(); V && V->Settings.WeightedBlendables.Array.IsValidIndex(M.Index))
			{
				V->Settings.WeightedBlendables.Array[M.Index].Weight = M.Weight;
			}
		}
		UE_LOG(LogSovereignRealms, Log, TEXT("title: silhouettes back (%d blendable(s))"), MutedSilhouettes.Num());
		MutedSilhouettes.Reset();
	}
}

// ------------------------------------------------------------------------------------------------ primitives

void AVLHUD::Fill(float X, float Y, float W, float H, const FLinearColor& Color)
{
	if (W > 0.f && H > 0.f && Color.A > 0.f)
	{
		DrawRect(Lin(Color), X, Y, W, H);
	}
}

void AVLHUD::BeginRects()
{
	RectBatch = (CVarOptHud.GetValueOnGameThread() != 0 && Canvas && Canvas->Canvas && GWhiteTexture)
		? Canvas->Canvas->GetBatchedElements(FCanvas::ET_Triangle, nullptr, GWhiteTexture, SE_BLEND_Translucent) : nullptr;
}

void AVLHUD::EndRects()
{
	RectBatch = nullptr;
}

void AVLHUD::Rect(float X, float Y, float W, float H, const FLinearColor& Color)
{
	if (W > 0.f && H > 0.f && Color.A > 0.f)
	{
		RectLinear(X, Y, W, H, Lin(Color));
	}
}

void AVLHUD::RectLinear(float X, float Y, float W, float H, const FLinearColor& LinearColor)
{
	if (!(W > 0.f && H > 0.f && LinearColor.A > 0.f))
	{
		return;
	}
	if (!RectBatch)
	{
		DrawRect(LinearColor, X, Y, W, H);
		return;
	}
	// what FCanvasTileItem::Draw adds for AHUD::DrawRect's tile (GWhiteTexture, translucent, depth 1)
	FLinearColor Actual = LinearColor;
	Actual.A *= Canvas->Canvas->AlphaModulate;
	const FHitProxyId HitProxyId = Canvas->Canvas->GetHitProxyId();
	const float Left = float(double(X)), Top = float(double(Y)), Right = float(double(X) + double(W)), Bottom = float(double(Y) + double(H));
	const int32 V00 = RectBatch->AddVertexf(FVector4f(Left, Top, 0.f, 1.f), FVector2f(0.f, 0.f), Actual, HitProxyId);
	const int32 V10 = RectBatch->AddVertexf(FVector4f(Right, Top, 0.f, 1.f), FVector2f(1.f, 0.f), Actual, HitProxyId);
	const int32 V01 = RectBatch->AddVertexf(FVector4f(Left, Bottom, 0.f, 1.f), FVector2f(0.f, 1.f), Actual, HitProxyId);
	const int32 V11 = RectBatch->AddVertexf(FVector4f(Right, Bottom, 0.f, 1.f), FVector2f(1.f, 1.f), Actual, HitProxyId);
	RectBatch->AddTriangleExtensive(V00, V10, V11, nullptr, GWhiteTexture, SE_BLEND_Translucent);
	RectBatch->AddTriangleExtensive(V00, V11, V01, nullptr, GWhiteTexture, SE_BLEND_Translucent);
}

const AVLHUD::FUnitFrame& AVLHUD::UnitsThisFrame()
{
	if (UnitFrame.Frame != GFrameCounter)
	{
		UnitFrame.Frame = GFrameCounter;
		UnitFrame.Live.Reset();
		if (const UVLBattle* Battle = UVLBattle::Get(this))
		{
			for (AVLKing* Unit : Battle->AllUnits())
			{
				if (!Unit->IsDead() && !UVLFog::HidesUnit(Unit))      // (an enemy in the fog of war: no bar, diamond or dot)
				{
					UnitFrame.Live.Add(Unit);
				}
			}
		}
		else
		{
			for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
			{
				if (!It->IsDead())
				{
					UnitFrame.Live.Add(*It);
				}
			}
		}
		UnitFrame.Platoon.Reset();
		UnitFrame.Selected.Reset();
		if (const UVLCommand* Command = UVLCommand::Get(this))
		{
			Command->GetPlatoonMap(UnitFrame.Platoon);
			Command->GetSelectionSet(UnitFrame.Selected);
		}
	}
	return UnitFrame;
}

AActor* AVLHUD::HoverPick()
{
	const APlayerCameraManager* Cam = PCtrl ? PCtrl->PlayerCameraManager.Get() : nullptr;
	const FVector Eye = Cam ? Cam->GetCameraLocation() : FVector::ZeroVector;
	const FRotator Rot = Cam ? Cam->GetCameraRotation() : FRotator::ZeroRotator;
	const float FOV = Cam ? Cam->GetFOVAngle() : 0.f;
	const bool bSame = bHoverKnown && CVarOptHud.GetValueOnGameThread() != 0 && Mouse == HoverMouse && Eye == HoverEye && Rot == HoverRot && FOV == HoverFOV
		&& GFrameCounter - HoverFrame < 4 && !HoverActor.IsStale();
	if (!bSame)
	{
		HoverActor = King->PickUnderCursor(PCtrl);
		HoverMouse = Mouse;
		HoverEye = Eye;
		HoverRot = Rot;
		HoverFOV = FOV;
		HoverFrame = GFrameCounter;
		bHoverKnown = true;
	}
	return HoverActor.Get();
}

void AVLHUD::Outline(const FBox2D& Box, const FLinearColor& Color, float T)
{
	const float X = Box.Min.X, Y = Box.Min.Y, W = Box.Max.X - Box.Min.X, H = Box.Max.Y - Box.Min.Y;
	Fill(X, Y, W, T, Color);
	Fill(X, Y + H - T, W, T, Color);
	Fill(X, Y + T, T, H - 2.f * T, Color);
	Fill(X + W - T, Y + T, T, H - 2.f * T, Color);
}

void AVLHUD::Panel(const FBox2D& Box, bool bOrnate, float Alpha)
{
	const float X = Box.Min.X, Y = Box.Min.Y, W = Box.Max.X - Box.Min.X, H = Box.Max.Y - Box.Min.Y;
	const float B = FMath::Max(1.f, U(2.f)), I = FMath::Max(1.f, U(1.f));
	Fill(X + B, Y + 2.f * B, W, H, A(FLinearColor(0.f, 0.f, 0.f, 0.40f), Alpha));          // drop shadow
	Fill(X, Y, W, H, A(Bronze, Alpha));
	Fill(X + B, Y + B, W - 2.f * B, H - 2.f * B, A(PanelFill, Alpha));
	Fill(X + B, Y + B, W - 2.f * B, FMath::RoundToFloat(FMath::Min(H * 0.4f, U(46.f))), A(PanelSheen, Alpha * 0.55f));   // a lighter top: a slight sheen
	// a thin gold rule inside the bronze
	const float G = B + (bOrnate ? U(4.f) : U(2.f));
	Outline(FBox2D(FVector2D(X + G, Y + G), FVector2D(X + W - G, Y + H - G)), A(Gold, Alpha * (bOrnate ? 0.55f : 0.32f)), I);
	// corner brackets
	const float L = U(bOrnate ? 16.f : 9.f), T = FMath::Max(1.f, U(2.f));
	for (int32 c = 0; c < 4; ++c)
	{
		const bool bR = (c & 1) != 0, bD = (c & 2) != 0;
		const float CX = bR ? X + W - G : X + G, CY = bD ? Y + H - G : Y + G;
		Fill(bR ? CX - L : CX, bD ? CY - T : CY, L, T, A(GoldBright, Alpha));
		Fill(bR ? CX - T : CX, bD ? CY - L : CY, T, L, A(GoldBright, Alpha));
		if (bOrnate)
		{
			const float D = U(4.f);
			Fill((bR ? CX - U(8.f) - D : CX + U(8.f)), (bD ? CY - U(8.f) - D : CY + U(8.f)), D, D, A(Gold, Alpha));
		}
	}
}

void AVLHUD::HudPanel(const FBox2D& Box)
{
	Panel(Box);
	Block(Box);
}

FSlateFontInfo AVLHUD::Font(float Pixels, int32 Weight) const
{
	static const FName Faces[] = { TEXT("Regular"), TEXT("Bold"), TEXT("Black"), TEXT("BoldCondensed") };
	// Slate sizes are points at 96 dpi; snap to half points so the glyph cache holds a handful of sizes, not hundreds.
	return FCoreStyle::GetDefaultFontStyle(Faces[FMath::Clamp(Weight, 0, 3)], FMath::Max(5.f, FMath::RoundToFloat(Pixels * 0.75f * 2.f) * 0.5f));
}

FVector2D AVLHUD::TextSize(const FString& String, float Pixels, int32 Weight, float Spacing) const
{
	if (!FSlateApplication::IsInitialized())
	{
		return FVector2D(String.Len() * Pixels * 0.5f, Pixels * 1.2f);
	}
	const TSharedRef<FSlateFontMeasure> Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
	const FSlateFontInfo F = Font(Pixels, Weight);
	return FVector2D(Measure->Measure(String, F, DpiScale).X / DpiScale + Spacing * String.Len(), Measure->GetMaxCharacterHeight(F, DpiScale) / DpiScale);
}

float AVLHUD::Text(const FString& String, float X, float Y, float Pixels, const FLinearColor& Color, int32 Align, int32 Weight, float Spacing, bool bShadow)
{
	if (String.IsEmpty() || Color.A <= 0.f || !UIFont)
	{
		return 0.f;
	}
	const float W = TextSize(String, Pixels, Weight, Spacing).X;
	if (Align == AlignCentre) { X -= W * 0.5f; }
	else if (Align == AlignRight) { X -= W; }
	FCanvasTextItem Item(FVector2D(FMath::RoundToFloat(X), FMath::RoundToFloat(Y)), FText::FromString(String), Font(Pixels, Weight), Lin(Color));
	Item.Font = UIFont;
	Item.HorizSpacingAdjust = Spacing;
	if (bShadow)
	{
		const float Off = FMath::Max(1.f, FMath::RoundToFloat(Pixels / 14.f));
		Item.EnableShadow(FLinearColor(0.f, 0.f, 0.f, 0.8f * Color.A), FVector2D(Off, Off));
	}
	Canvas->DrawItem(Item);
	return W;
}

float AVLHUD::TextIn(const FBox2D& Box, const FString& String, float Pixels, const FLinearColor& Color, int32 Align, int32 Weight, float Spacing, bool bShadow)
{
	const float H = TextSize(String, Pixels, Weight, Spacing).Y;
	const float X = Align == AlignCentre ? (Box.Min.X + Box.Max.X) * 0.5f : (Align == AlignRight ? Box.Max.X : Box.Min.X);
	return Text(String, X, (Box.Min.Y + Box.Max.Y - H) * 0.5f, Pixels, Color, Align, Weight, Spacing, bShadow);
}

void AVLHUD::Icon(EVLIcon Which, float X, float Y, float Size, const FLinearColor& Tint, bool bEnemy)
{
	if (!IconAtlas)
	{
		return;
	}
	// atlas: 8 columns of 18 px cells (a 16 px icon and a 1 px gutter); the lower half of the rows are the enemy-red
	// copies. The row count is read off the texture, so the atlas can grow without a change here.
	const float AtlasH = FMath::Max(float(IconAtlas->GetSizeY()), 36.f);
	const int32 HalfRows = FMath::Max(1, FMath::RoundToInt(AtlasH / 36.f));
	const int32 N = int32(Which);
	const float Col = float(N % 8), Row = float(N / 8 + (bEnemy ? HalfRows : 0));
	DrawTexture(IconAtlas, FMath::RoundToFloat(X), FMath::RoundToFloat(Y), FMath::RoundToFloat(Size), FMath::RoundToFloat(Size),
		(Col * 18.f + 1.f) / 144.f, (Row * 18.f + 1.f) / AtlasH, 16.f / 144.f, 16.f / AtlasH, Lin(Tint), BLEND_Translucent);
}

void AVLHUD::Portrait(EVLPortrait Which, float X, float Y, float Size, const FLinearColor& Tint, bool bEnemy)
{
	if (!PortraitAtlas || PortraitAtlas->GetSizeY() <= 0)
	{
		// (no atlas imported yet: the main game's pixel portraits)
		static const EVLIcon Old[5] = { EVLIcon::Crown, EVLIcon::PortraitShield, EVLIcon::PortraitArcher, EVLIcon::PortraitScout, EVLIcon::PortraitBuilder };
		Icon(Old[FMath::Clamp(int32(Which), 0, 4)], X, Y, Size, Tint, bEnemy);
		return;
	}
	// one row of square cells
	const float Cells = FMath::Max(1.f, FMath::RoundToFloat(float(PortraitAtlas->GetSizeX()) / PortraitAtlas->GetSizeY()));
	const FLinearColor T = bEnemy ? FLinearColor(Tint.R, Tint.G * 0.78f, Tint.B * 0.74f, Tint.A) : Tint;
	DrawTexture(PortraitAtlas, FMath::RoundToFloat(X), FMath::RoundToFloat(Y), FMath::RoundToFloat(Size), FMath::RoundToFloat(Size),
		float(int32(Which)) / Cells, 0.f, 1.f / Cells, 1.f, Lin(T), BLEND_Translucent);
}

void AVLHUD::Meter(float X, float Y, float W, float H, float Frac, const FLinearColor& FillColor)
{
	const float B = FMath::Max(1.f, U(1.f));
	const float FW = FMath::RoundToFloat(W * FMath::Clamp(Frac, 0.f, 1.f));
	Fill(X - B, Y - B, W + 2.f * B, H + 2.f * B, A(Bronze, FillColor.A));
	Fill(X, Y, W, H, A(FLinearColor(0.012f, 0.016f, 0.028f, 1.f), FillColor.A));
	Fill(X, Y, FW, H, FillColor);
	Fill(X, Y, FW, FMath::Max(1.f, FMath::RoundToFloat(H * 0.3f)), FLinearColor(1.f, 1.f, 1.f, 0.22f * FillColor.A));
}

void AVLHUD::KeyCap(const FString& Key, float RightX, float Y, bool bEnabled)
{
	const float P = U(13.f);
	const float W = FMath::Max(U(19.f), TextSize(Key, P, Bold).X + U(9.f)), H = U(19.f);
	const FBox2D Box(FVector2D(RightX - W, Y), FVector2D(RightX, Y + H));
	Fill(Box.Min.X, Box.Min.Y, W, H, bEnabled ? Gold : A(Bronze, 0.9f));
	const float B = FMath::Max(1.f, U(1.f));
	Fill(Box.Min.X + B, Box.Min.Y + B, W - 2.f * B, H - 2.f * B, FLinearColor(0.02f, 0.028f, 0.05f, 1.f));
	TextIn(Box, Key, P, bEnabled ? GoldBright : Dim, AlignCentre, Bold, 0.f, false);
}

void AVLHUD::Rule(float X, float Y, float W, float Alpha)
{
	// a gold hairline with a small diamond at its middle
	const float T = FMath::Max(1.f, U(1.f)), D = U(3.f);
	Fill(X, Y, W, T, A(Gold, 0.55f * Alpha));
	const float CX = FMath::RoundToFloat(X + W * 0.5f);
	Fill(CX - D, Y - T, 2.f * D, 3.f * T, A(GoldBright, Alpha));
	Fill(CX - T, Y - D, 2.f * T, 2.f * D + T, A(GoldBright, Alpha));
}

FBox2D AVLHUD::Pill(const FString& Label, float X, float Y, float Pixels, EVLIcon Which, const FLinearColor& Accent, float Alpha, bool bCentre)
{
	const float IS = FMath::RoundToFloat(Pixels * 1.35f), Pad = FMath::RoundToFloat(Pixels * 0.6f);
	const float H = FMath::RoundToFloat(Pixels * 1.95f);
	const float W = Pad + U(4.f) + IS + Pad * 0.6f + TextSize(Label, Pixels, Bold).X + Pad;
	if (bCentre) { X -= W * 0.5f; }
	X = FMath::RoundToFloat(FMath::Clamp(X, U(6.f), FMath::Max(U(6.f), View.X - W - U(6.f))));
	Y = FMath::RoundToFloat(Y);
	const float B = FMath::Max(1.f, U(1.f));
	Fill(X + B, Y + 2.f * B, W, H, FLinearColor(0.f, 0.f, 0.f, 0.35f * Alpha));
	Fill(X, Y, W, H, A(Accent, 0.75f * Alpha));
	Fill(X + B, Y + B, W - 2.f * B, H - 2.f * B, A(PanelFill, Alpha * 1.05f));
	Fill(X + B, Y + B, U(4.f), H - 2.f * B, A(Accent, Alpha));
	Icon(Which, X + Pad + U(4.f), Y + (H - IS) * 0.5f, IS, FLinearColor(1.f, 1.f, 1.f, Alpha));
	const FBox2D Box(FVector2D(X, Y), FVector2D(X + W, Y + H));
	TextIn(FBox2D(FVector2D(X + Pad + U(4.f) + IS + Pad * 0.6f, Y), Box.Max), Label, Pixels, A(Parchment, Alpha), AlignLeft, Bold);
	return Box;
}

void AVLHUD::ButtonFrame(const FBox2D& Box, const FBtn& B, bool bEnabled, bool bActive)
{
	const float Down = B.bHeld ? FMath::Max(1.f, U(1.f)) : 0.f;
	const float X = Box.Min.X, Y = Box.Min.Y + Down, W = Box.Max.X - Box.Min.X, H = Box.Max.Y - Box.Min.Y;
	const float E = FMath::Max(1.f, U(2.f));
	const FLinearColor Border = !bEnabled ? A(Bronze, 0.75f) : (bActive ? GoldBright : FMath::Lerp(A(Gold, 0.8f), GoldBright, B.Hot));
	FLinearColor Body = !bEnabled ? ButtonOff : FMath::Lerp(ButtonFill, ButtonHot, B.bHeld ? 0.3f : B.Hot);
	if (bActive) { Body = FMath::Lerp(Body, FLinearColor(0.30f, 0.22f, 0.07f, 0.98f), 0.6f); }
	Fill(X, Y, W, H, Border);
	Fill(X + E, Y + E, W - 2.f * E, H - 2.f * E, Body);
	if (bEnabled) { Fill(X + E, Y + E, W - 2.f * E, FMath::RoundToFloat(H * 0.42f), FLinearColor(1.f, 1.f, 1.f, 0.035f + 0.04f * B.Hot)); }
}

AVLHUD::FBtn AVLHUD::IconButton(const FBox2D& Box, uint32 Id, EVLIcon Which, const TCHAR* Key, bool bEnabled, bool bActive)
{
	const FBtn B = Button(Box, Id, bEnabled);
	ButtonFrame(Box, B, bEnabled, bActive);
	const float W = Box.Max.X - Box.Min.X, H = Box.Max.Y - Box.Min.Y;
	const float S = FMath::RoundToFloat(FMath::Min(W, H) * 0.58f);
	Icon(Which, Box.Min.X + (W - S) * 0.5f, Box.Min.Y + (H - S) * 0.5f + (B.bHeld ? U(1.f) : 0.f) + (Key ? U(3.f) : 0.f), S, bEnabled ? FLinearColor::White : FLinearColor(0.4f, 0.4f, 0.45f, 0.8f));
	if (Key) { KeyCap(Key, Box.Max.X - U(3.f), Box.Min.Y + U(3.f), bEnabled); }
	return B;
}

bool AVLHUD::MenuButton(const FBox2D& Box, uint32 Id, const FString& Label, bool bEnabled, bool bSelected)
{
	const FBtn B = Button(Box, Id, bEnabled);
	const float X = Box.Min.X, Y = Box.Min.Y + (B.bHeld ? U(1.f) : 0.f), W = Box.Max.X - Box.Min.X, H = Box.Max.Y - Box.Min.Y;
	const float Hot = bSelected ? 1.f : B.Hot;
	Fill(X, Y, W, H, FMath::Lerp(A(Bronze, 0.85f), GoldBright, Hot));
	const float E = FMath::Max(1.f, U(2.f));
	Fill(X + E, Y + E, W - 2.f * E, H - 2.f * E, bSelected ? FLinearColor(0.20f, 0.15f, 0.05f, 0.97f) : FMath::Lerp(ButtonFill, ButtonHot, Hot));
	Fill(X + E, Y + E, W - 2.f * E, FMath::RoundToFloat(H * 0.45f), FLinearColor(1.f, 1.f, 1.f, 0.03f + 0.03f * Hot));
	// gold accent on the left, growing with the hover
	Fill(X + E, Y + E, U(4.f) + U(6.f) * Hot, H - 2.f * E, FMath::Lerp(Gold, GoldBright, Hot));
	const FBox2D Inner(FVector2D(X + U(26.f) + U(6.f) * Hot, Y), FVector2D(X + W - U(12.f), Y + H));
	TextIn(Inner, Label, U(21.f), bEnabled ? FMath::Lerp(Parchment, GoldBright, Hot) : Dim, AlignLeft, Bold, U(1.f));
	if (B.bClicked) { Click(); }
	return B.bClicked;
}

bool AVLHUD::Slider(const FBox2D& Box, uint32 Id, float& Value, float Min, float Max)
{
	const FBtn B = Button(Box, Id);
	const float X = Box.Min.X, W = Box.Max.X - Box.Min.X, CY = (Box.Min.Y + Box.Max.Y) * 0.5f;
	const float Knob = U(14.f);
	bool bChanged = false;
	// held and dragged; a single click (also a scripted one) sets it where it lands
	if ((B.bHeld || B.bClicked) && W > Knob)
	{
		const float Px = B.bHeld && bMouse ? Mouse.X : Press.Pos.X;
		const float V = Min + FMath::Clamp((Px - X - Knob * 0.5f) / (W - Knob), 0.f, 1.f) * (Max - Min);
		bChanged = !FMath::IsNearlyEqual(V, Value, 0.0005f);
		Value = V;
	}
	const float T = FMath::Clamp((Value - Min) / (Max - Min), 0.f, 1.f);
	const float TH = U(8.f);
	Meter(X, FMath::RoundToFloat(CY - TH * 0.5f), W, TH, T, FMath::Lerp(Gold, GoldBright, B.Hot));
	const float KX = FMath::RoundToFloat(X + T * (W - Knob));
	Fill(KX, CY - U(11.f), Knob, U(22.f), B.bHeld || B.bHover ? GoldBright : Gold);
	Fill(KX + U(2.f), CY - U(9.f), Knob - U(4.f), U(18.f), FLinearColor(0.10f, 0.13f, 0.21f, 1.f));
	Fill(KX + U(6.f), CY - U(5.f), U(2.f), U(10.f), GoldBright);
	return bChanged;
}

void AVLHUD::SetTooltip(const FBox2D& Anchor, const FString& Title, const TArray<FString>& Lines)
{
	bTooltip = true;
	TooltipAnchor = Anchor;
	TooltipTitle = Title;
	TooltipLines = Lines;
}

bool AVLHUD::AltHeld() const
{
	return PCtrl && (PCtrl->IsInputKeyDown(EKeys::LeftAlt) || PCtrl->IsInputKeyDown(EKeys::RightAlt));
}

void AVLHUD::DrawTooltip()
{
	// (the owner's call, 2026-11-22: the cards over buttons show only while Option / Alt is held)
	if (!bTooltip || !AltHeld())
	{
		return;
	}
	// warm parchment, dark ink: reads as a note laid over the dark panels
	const float Pad = U(12.f), TP = U(18.f), LP = U(15.f), LH = U(21.f);
	float W = TextSize(TooltipTitle, TP, Bold).X;
	for (const FString& L : TooltipLines) { W = FMath::Max(W, TextSize(L, LP, Regular).X); }
	W += 2.f * Pad;
	const float H = 2.f * Pad + U(24.f) + TooltipLines.Num() * LH;
	float X = TooltipAnchor.Max.X + U(10.f), Y = TooltipAnchor.Min.Y;
	if (X + W > View.X - U(8.f)) { X = TooltipAnchor.Min.X - U(10.f) - W; }
	if (X < U(8.f)) { X = FMath::Clamp(TooltipAnchor.Min.X, U(8.f), View.X - W - U(8.f)); Y = TooltipAnchor.Min.Y - H - U(10.f); }
	Y = FMath::Clamp(Y, U(8.f), View.Y - H - U(8.f));
	X = FMath::RoundToFloat(X); Y = FMath::RoundToFloat(Y);
	const float B = FMath::Max(1.f, U(2.f));
	Fill(X + B, Y + 2.f * B, W, H, FLinearColor(0.f, 0.f, 0.f, 0.45f));
	Fill(X, Y, W, H, Bronze);
	Fill(X + B, Y + B, W - 2.f * B, H - 2.f * B, ParchmentFill);
	Fill(X + B, Y + B, W - 2.f * B, U(3.f), FLinearColor(1.f, 1.f, 1.f, 0.25f));
	Text(TooltipTitle, X + Pad, Y + Pad - U(2.f), TP, Ink, AlignLeft, Bold, 0.f, false);
	Fill(X + Pad, Y + Pad + U(23.f), W - 2.f * Pad, FMath::Max(1.f, U(1.f)), A(Bronze, 0.8f));
	for (int32 i = 0; i < TooltipLines.Num(); ++i)
	{
		Text(TooltipLines[i], X + Pad, Y + Pad + U(28.f) + i * LH, LP, A(Ink, 0.92f), AlignLeft, Regular, 0.f, false);
	}
}

FVector AVLHUD::Project(const FVector& World) const
{
	return Canvas ? Canvas->Project(World) : FVector(0.f, 0.f, -1.f);
}

float AVLHUD::GroundZ(const FVector2D& At, float Fallback) const
{
	if (const UVLGrid* Grid = UVLGrid::Get(this); Grid && Grid->IsBuilt())
	{
		const int32 Node = Grid->NodeAt(FVector(At.X, At.Y, Fallback), 400.f);
		if (Node != INDEX_NONE)
		{
			return Grid->NodePos(Node).Z;
		}
	}
	return Fallback;
}

void AVLHUD::Ring(const FVector& Centre, float Radius, const FLinearColor& Colour, float Thickness, int32 Sides)
{
	FVector Prev = FVector::ZeroVector;
	for (int32 i = 0; i <= Sides; ++i)
	{
		const float Ang = 2.f * PI * i / Sides;
		const FVector P = Project(Centre + FVector(FMath::Cos(Ang), FMath::Sin(Ang), 0.f) * Radius);
		if (i > 0 && P.Z > 0.f && Prev.Z > 0.f)
		{
			DrawLine(Prev.X, Prev.Y, P.X, P.Y, Colour, Thickness);
		}
		Prev = P;
	}
}

// ------------------------------------------------------------------------------------------------ world-space feedback

void AVLHUD::SelectedUnits(TArray<AVLKing*>& Out) const
{
	Out.Reset();
	const UVLCommand* Command = UVLCommand::Get(this);
	if (!King || King->IsHeroMode() || !Command)
	{
		return;
	}
	Command->GetSelection(Out);
	if (Out.Num() == 0)
	{
		// a unit of the enemy's (it cannot be commanded: only looked at)
		if (AVLKing* One = Cast<AVLKing>(King->GetSelected()); One && One->IsAlive())
		{
			Out.Add(One);
		}
	}
}

namespace
{
	TAutoConsoleVariable<int32> CVarTeamRings(TEXT("vl.TeamRings"), 0,
		TEXT("1: a ring of the side's colour under every unit (off by default: the platoon diamond over their heads and the health bars mark them)"));
}

void AVLHUD::DrawUnitRings()
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!PCtrl || !King || !Battle || Battle->GetState() == EVLMatch::Idle)
	{
		return;
	}
	const FVector Eye = PCtrl->PlayerCameraManager ? PCtrl->PlayerCameraManager->GetCameraLocation() : FVector::ZeroVector;
	TArray<AVLKing*> Sel;
	SelectedUnits(Sel);
	const bool bHero = King->IsHeroMode();
	AActor* Under = (!bHero && bMouse && !IsOverUI(Mouse / ToCanvas)) ? HoverPick() : nullptr;
	if (bHero || !bMouse)
	{
		bHoverKnown = false;
	}
	// a ring of its side's colour at every unit's feet: hidden by default (the user's call: the platoon tag over their
	// heads, the health bars and the far pips show who is whose; vl.TeamRings 1 brings it back). The main game's green
	// ring under the selected and the pale one under the pointer are left out too.
	static const TArray<AVLKing*> NoUnits;
	for (AVLKing* Un : CVarTeamRings.GetValueOnGameThread() != 0 ? UnitsThisFrame().Live : NoUnits)
	{
		if (Un->IsDead() || (Un == King && bHero) || FVector::DistSquared(Eye, Un->GetActorLocation()) > FMath::Square(26000.f))
		{
			continue;
		}
		const FLinearColor TC = UVLBattle::TeamColour(Un->Team);
		Ring(Un->GetFeet() + FVector(0.f, 0.f, 5.f), 46.f, FLinearColor(TC.R, TC.G, TC.B, 0.75f), FMath::Max(1.f, U(1.6f)), 20);
	}
	// a building: the selected one's footprint in green (an enemy's red), the one under the pointer pale
	auto Footprint = [&](AActor* B, const FLinearColor& Col, float Th)
	{
		const UStaticMeshComponent* SMC = B ? B->FindComponentByClass<UStaticMeshComponent>() : nullptr;
		if (!SMC || !SMC->GetStaticMesh())
		{
			return;
		}
		const FTransform T = SMC->GetComponentTransform();
		const FBox Box = SMC->GetStaticMesh()->GetBoundingBox();
		const float Pad = 60.f;
		const FVector C[4] = { FVector(Box.Min.X, Box.Min.Y, 0.f), FVector(Box.Max.X, Box.Min.Y, 0.f), FVector(Box.Max.X, Box.Max.Y, 0.f), FVector(Box.Min.X, Box.Max.Y, 0.f) };
		const FVector Mid = T.TransformPosition(Box.GetCenter());
		for (int32 i = 0; i < 4; ++i)
		{
			FVector P0 = T.TransformPosition(FVector(C[i].X, C[i].Y, Box.Min.Z)), P1 = T.TransformPosition(FVector(C[(i + 1) % 4].X, C[(i + 1) % 4].Y, Box.Min.Z));
			P0 += (P0 - Mid).GetSafeNormal2D() * Pad;
			P1 += (P1 - Mid).GetSafeNormal2D() * Pad;
			const int32 N = 16;
			FVector Prev = FVector::ZeroVector;
			for (int32 k = 0; k <= N; ++k)
			{
				const FVector W = FMath::Lerp(P0, P1, float(k) / N);
				const FVector S = Project(FVector(W.X, W.Y, GroundZ(FVector2D(W), W.Z) + 15.f));
				if (k > 0 && S.Z > 0.f && Prev.Z > 0.f)
				{
					DrawLine(Prev.X, Prev.Y, S.X, S.Y, Col, Th);
				}
				Prev = S;
			}
		}
	};
	if (AActor* B = SelectedBuilding())
	{
		Footprint(B, Battle->TeamOf(B) == UVLBattle::Enemy ? EnemyRing : SelectionRing, FMath::Max(1.f, U(2.5f)));
	}
	if (Under && !Cast<AVLKing>(Under) && Under != King->GetSelected() && Battle->FindBuilding(Under))
	{
		Footprint(Under, Battle->IsHostile(Under, UVLBattle::Player) ? FLinearColor(EnemyRing.R, EnemyRing.G, EnemyRing.B, 0.6f) : HoverRing, FMath::Max(1.f, U(1.5f)));
	}
}

void AVLHUD::DrawSelectionBox()
{
	FVector2D P0, P1;
	if (!King || King->IsHeroMode() || !King->GetSelectionBox(P0, P1))
	{
		return;
	}
	P0 *= ToCanvas;
	P1 *= ToCanvas;
	const FBox2D Box(FVector2D(FMath::Min(P0.X, P1.X), FMath::Min(P0.Y, P1.Y)), FVector2D(FMath::Max(P0.X, P1.X), FMath::Max(P0.Y, P1.Y)));
	Fill(Box.Min.X, Box.Min.Y, Box.Max.X - Box.Min.X, Box.Max.Y - Box.Min.Y, FromLinear(BoxFill));
	Outline(Box, FromLinear(BoxLine), FMath::Max(1.f, U(2.f)));
}

namespace
{
	/** A building's label point: over its roof. */
	FVector LabelPoint(const AActor* A)
	{
		FVector Origin, Extent;
		A->GetActorBounds(true, Origin, Extent);
		return Origin + FVector(0.f, 0.f, Extent.Z + 60.f);
	}

	/** How many progress rows DrawTrainingBars stacks over a building (training, upgrade), so the health bar can sit
	 *  above them. */
	int32 OverheadRows(const FVLBuildingState& B)
	{
		return (B.Queue.Num() > 0 ? 1 : 0) + ((B.Team == UVLBattle::Player && B.UpgradeLeft >= 0.f) ? 1 : 0);
	}
}

void AVLHUD::DrawHealthBars()
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	const UVLCommand* Command = UVLCommand::Get(this);
	if (!Battle || !King || Battle->GetState() == EVLMatch::Idle)
	{
		return;
	}
	const double WorldNow = GetWorld()->GetTimeSeconds();
	const float B = FMath::Max(1.f, U(1.f));
	const bool bHero = King->IsHeroMode();

	auto Bar = [&](const FVector& WorldPoint, float W, float H, float Frac, bool bEnemy, float Lift = 0.f, float Alpha = 1.f)
	{
		const FVector S = Project(WorldPoint);
		if (S.Z <= 0.f || Alpha <= 0.f)
		{
			return;
		}
		const float X = FMath::RoundToFloat(S.X - W * 0.5f), Y = FMath::RoundToFloat(S.Y - H - Lift);
		// enemies get a red-tinted frame so the sides read at a glance
		Rect(X - B, Y - B, W + 2.f * B, H + 2.f * B, A(bEnemy ? FLinearColor(0.30f, 0.03f, 0.02f, 0.92f) : FLinearColor(0.02f, 0.03f, 0.07f, 0.92f), Alpha));
		Rect(X, Y, W, H, FLinearColor(0.10f, 0.10f, 0.11f, 0.9f * Alpha));
		Rect(X, Y, FMath::RoundToFloat(W * Frac), H, A(Health(Frac), Alpha));
		Rect(X, Y, FMath::RoundToFloat(W * Frac), FMath::Max(1.f, FMath::RoundToFloat(H * 0.3f)), FLinearColor(1.f, 1.f, 1.f, 0.25f * Alpha));
	};

	const AActor* Sel = King->GetSelected();
	for (auto It = BarSeen.CreateIterator(); It; ++It)
	{
		if (!It.Key().IsValid() || It.Key()->IsDead()) { It.RemoveCurrent(); }
	}
	// (B: the frame's one list of the living, the selection as a set, and the bars' rectangles in one batch)
	const bool bFast = CVarOptHud.GetValueOnGameThread() != 0;
	const FUnitFrame& Frame = UnitsThisFrame();
	BeginRects();
	for (AVLKing* Unit : Frame.Live)
	{
		if (Unit->IsDead() || (Unit == King && bHero))
		{
			continue;       // (the unit the player plays has its own bar, bottom middle)
		}
		// Only when it matters (both sides, every view): in the red always; otherwise for a few seconds after its health
		// changed (a hit or a heal), then it fades; and while it is selected, as in the main game.
		const float Frac = Unit->GetHealthFrac();
		FBarSeen& Seen = BarSeen.FindOrAdd(Unit);
		if (Seen.Health < 0.f) { Seen.Health = Frac; }
		else if (!FMath::IsNearlyEqual(Seen.Health, Frac, 0.0005f)) { Seen.Health = Frac; Seen.ChangedAt = Now; }
		const float Since = float(Now - Seen.ChangedAt);
		const bool bRed = Frac < HealthBarRed;
		// (the hero view's selection too: it is commanded from there with the crosshair)
		const bool bSelected = (Command && (bFast ? Frame.Selected.Contains(Unit) : Command->IsSelected(Unit))) || (!bHero && Sel == Unit);
		const float Alpha = (bSelected || bRed) ? 1.f : FMath::Clamp(1.f - (Since - HealthBarLinger) / HealthBarFade, 0.f, 1.f);
		if (Alpha <= 0.f)
		{
			continue;
		}
		Bar(Unit->GetActorLocation() + FVector(0.f, 0.f, 120.f), U(HealthBarW), FMath::Max(3.f, U(HealthBarH + 1.f)), Frac, Unit->Team == UVLBattle::Enemy, 0.f, Alpha);
	}
	EndRects();
	for (const FVLBuildingState& Bs : Battle->GetBuildings())
	{
		if (!Bs.IsAlive() || Bs.Team == UVLBattle::Neutral || !UVLFog::InSight(Bs.Actor.Get()))
		{
			continue;
		}
		const float Frac = Bs.Health / FMath::Max(Bs.MaxHealth, 1.f);
		const bool bRecentlyHurt = Frac < 1.f && (WorldNow - Bs.LastHit) < HealthBarLinger;
		if (!bRecentlyHurt && !(Bs.Actor.Get() == Sel && Frac < 1.f))
		{
			continue;
		}
		// over the progress rows (training, upgrade) rather than hidden by them
		const int32 Rows = OverheadRows(Bs);
		Bar(LabelPoint(Bs.Actor.Get()), U(110.f), U(8.f), Frac, Bs.Team == UVLBattle::Enemy, Rows > 0 ? Rows * U(26.f) - U(4.f) : 0.f);
	}
}

void AVLHUD::DrawPlatoonTags()
{
	// A numbered tag in the platoon's colour floats over each platoon, so it can be told apart at a glance: over its
	// leader, crowned, if it has one. In the hero view only the platoons of the selection (and never over the head
	// of the unit played).
	const UVLCommand* Command = UVLCommand::Get(this);
	if (!Command || !King)
	{
		return;
	}
	const bool bHero = King->IsHeroMode();
	TArray<AVLKing*> Sel;
	Command->GetSelection(Sel);
	const int32 SelectedPlatoon = Command->PlatoonOf(Sel);
	for (int32 i = 0; i < UVLCommand::MaxPlatoons; ++i)
	{
		TArray<AVLKing*> Members;
		Command->GetPlatoon(i, Members);
		if (Members.Num() == 0 || (bHero && !Members.ContainsByPredicate([&Sel](const AVLKing* M) { return Sel.Contains(M); })))
		{
			continue;
		}
		const AVLKing* Leader = Command->GetPlatoonLeader(i);
		if (bHero && Leader == King)
		{
			Leader = nullptr;
		}
		// over the leader, or the member nearest the platoon's middle, a little above the heads
		FVector2D Mid = FVector2D::ZeroVector;
		for (const AVLKing* M : Members) { Mid += FVector2D(M->GetActorLocation()); }
		Mid /= Members.Num();
		const AVLKing* Anchor = Leader;
		float Best = TNumericLimits<float>::Max();
		for (const AVLKing* M : Members)
		{
			const float D = FVector2D::DistSquared(FVector2D(M->GetActorLocation()), Mid);
			if (!Leader && !(bHero && M == King) && D < Best) { Best = D; Anchor = M; }
		}
		if (!Anchor)
		{
			continue;
		}
		const FVector S = Project(Anchor->GetActorLocation() + FVector(0.f, 0.f, 190.f));
		if (S.Z <= 0.f || S.X < -50.f || S.Y < -50.f || S.X > View.X + 50.f || S.Y > View.Y + 50.f)
		{
			continue;
		}
		const FLinearColor Col = PlatoonColor(i);
		const bool bSel = SelectedPlatoon == i;
		const float H = U(bSel ? 24.f : 20.f), W = H * 0.9f;
		const float X = FMath::RoundToFloat(S.X - W * 0.5f), Y = FMath::RoundToFloat(S.Y - H);
		Fill(X - 1.f, Y - 1.f, W + 2.f, H + 2.f, FLinearColor(0.02f, 0.02f, 0.03f, 0.9f));
		Fill(X, Y, W, H, FLinearColor(Col.R * 0.25f, Col.G * 0.25f, Col.B * 0.25f, 0.92f));
		Outline(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), Col, FMath::Max(1.f, U(bSel ? 2.f : 1.5f)));
		// a little pointer down to the troops
		for (float k = 0.f; k < U(5.f); k += 1.f)
		{
			const float w = U(5.f) - k;
			Fill(FMath::RoundToFloat(S.X - w), Y + H + k, FMath::Max(1.f, 2.f * w), 1.f, Col);
		}
		TextIn(FBox2D(FVector2D(X, Y), FVector2D(X + W, Y + H)), FString::FromInt(i + 1), H * 0.8f, Col, AlignCentre, Black);
		if (Anchor == Leader)
		{
			// the leader's crown on its tag
			const float CS = U(bSel ? 22.f : 19.f);
			Icon(EVLIcon::Crown, FMath::RoundToFloat(S.X - CS * 0.5f), FMath::RoundToFloat(Y - CS * 0.82f), CS);
		}
		if (Command->GetRallyPlatoon() == i)
		{
			// the recruits' platoon: a little flag beside its tag (the platoon panel's flag)
			const float FS = U(bSel ? 20.f : 17.f);
			Icon(EVLIcon::RecruitFlag, FMath::RoundToFloat(X + W + U(2.f)), FMath::RoundToFloat(Y + H * 0.5f - FS * 0.6f), FS);
		}
	}
}

void AVLHUD::DrawPayoutPopups()
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!Battle)
	{
		return;
	}
	const float Life = 1.5f, RiseBy = 130.f;
	for (const FVLPopup& Popup : Battle->GetPopups())
	{
		const float T = FMath::Clamp(float(Now - Popup.Time) / Life, 0.f, 1.f);
		// rises fast, then drifts; pops in over the first tenth and fades over the last third
		const float Rise = 1.f - FMath::Square(1.f - T);
		const FVector S = Project(Popup.At + FVector(0.f, 0.f, RiseBy * Rise));
		if (S.Z <= 0.f)
		{
			continue;
		}
		const float Alpha = T > 0.66f ? 1.f - (T - 0.66f) / 0.34f : 1.f;
		const float Pop = T < 0.12f ? 1.f + 0.4f * (1.f - T / 0.12f) : 1.f;
		const float P = U(24.f) * Pop, IS = U(24.f) * Pop;
		const FString Label = FString::Printf(TEXT("+%d"), Popup.Amount);
		const float W = TextSize(Label, P, Bold).X;
		const float X = S.X - (W + U(5.f) + IS) * 0.5f, Y = S.Y - P * 0.6f;
		Text(Label, X, Y, P, A(Popup.bGold ? GoldBright : FoodColor, Alpha), AlignLeft, Bold);
		Icon(Popup.bGold ? EVLIcon::Coin : EVLIcon::Food, X + W + U(5.f), Y + P * 0.12f, IS, FLinearColor(1.f, 1.f, 1.f, Alpha));
	}
}

namespace
{
	TAutoConsoleVariable<float> CVarHeroPipNear(TEXT("vl.HeroPips.Near"), 500.f, TEXT("cm from the unit played within which a foe has no diamond over it in the hero view"));
	TAutoConsoleVariable<float> CVarHeroPipFull(TEXT("vl.HeroPips.Full"), 1200.f, TEXT("cm from the unit played from which a foe's diamond is fully shown in the hero view"));
	TAutoConsoleVariable<int32> CVarRouteGroup(TEXT("vl.RouteLines.GroupOver"), 7, TEXT("a platoon (or one group order) of more than this many walkers draws one pathway line, its leader's, not one each"));
}

void AVLHUD::DrawGuardMarks()
{
	const UVLCommand* Command = UVLCommand::Get(this);
	if (!Command || !King)
	{
		return;
	}
	TArray<AVLKing*> Wards;
	Command->GetGuardedUnits(Wards);
	const bool bHero = King->IsHeroMode();
	for (const AVLKing* W : Wards)
	{
		if (bHero && W == King)
		{
			continue;               // (never over the head of the unit played)
		}
		const FVector S = Project(W->GetActorLocation() + FVector(0.f, 0.f, 175.f));
		if (S.Z <= 0.f || S.X < -40.f || S.Y < -40.f || S.X > View.X + 40.f || S.Y > View.Y + 40.f)
		{
			continue;
		}
		// a gold-edged plate with the shield, beside where a platoon's tag would be
		const float Sz = U(22.f), X = FMath::RoundToFloat(S.X - Sz - U(12.f)), Y = FMath::RoundToFloat(S.Y - Sz);
		Fill(X - U(3.f), Y - U(3.f), Sz + U(6.f), Sz + U(6.f), A(GoldBright, 0.75f + 0.25f * FMath::Sin(float(Now) * 4.f)));
		Fill(X - U(1.f), Y - U(1.f), Sz + U(2.f), Sz + U(2.f), FLinearColor(0.02f, 0.03f, 0.06f, 0.92f));
		Icon(EVLIcon::Shield, X, Y, Sz);
	}
}

void AVLHUD::DrawUnitHighlight()
{
	// (HoverUnit is last frame's: the list is drawn after the world's feedback)
	const AVLKing* Un = HoverUnit.Get();
	if (!Un || !Un->IsAlive() || !King || King->IsHeroMode())
	{
		return;
	}
	const float Pulse = 0.5f + 0.5f * FMath::Sin(float(Now) * 7.f);
	const FLinearColor Col(GoldBright.R, GoldBright.G, GoldBright.B, 0.75f + 0.25f * Pulse);
	const FVector Feet = Un->GetFeet() + FVector(0.f, 0.f, 6.f);
	Ring(Feet, 70.f + 14.f * Pulse, Col, FMath::Max(2.f, U(3.f)), 28);
	Ring(Feet, 110.f + 20.f * Pulse, FLinearColor(Col.R, Col.G, Col.B, 0.45f), FMath::Max(1.f, U(2.f)), 28);
	const FVector S = Project(Un->GetActorLocation() + FVector(0.f, 0.f, 170.f));
	if (S.Z > 0.f)
	{
		// an arrow pointing down at it, bobbing
		const float Bob = U(6.f) * Pulse, AH = U(14.f);
		for (float k = 0.f; k < AH; k += 1.f)
		{
			const float w = AH - k;
			Fill(FMath::RoundToFloat(S.X - w), FMath::RoundToFloat(S.Y - AH - Bob + k), FMath::Max(1.f, 2.f * w), 1.f, Col);
		}
		Fill(FMath::RoundToFloat(S.X - U(4.f)), FMath::RoundToFloat(S.Y - AH - Bob - U(12.f)), U(8.f), U(12.f), Col);
	}
}

static TAutoConsoleVariable<int32> CVarPipTris(TEXT("vl.Opt.PipTris"), 0, TEXT("1: a far unit's diamond is two triangles a layer (not the default: its edges were not compared pixel for pixel with the rows). 0: a canvas row for each of its lines, as it was"));

void AVLHUD::DrawFarPips()
{
	const UVLCommand* Command = UVLCommand::Get(this);
	if (!PCtrl || !King || !PCtrl->PlayerCameraManager)
	{
		return;
	}
	// The hero view: the enemy's troops only, each under its diamond from HeroPipNear to HeroPipFull of the unit
	// played (nearer, the figure itself is plain to see), so foes read at a glance among trees and at a distance.
	const bool bHero = King->IsHeroMode();
	const float HeroNear = CVarHeroPipNear.GetValueOnGameThread(), HeroFull = FMath::Max(CVarHeroPipFull.GetValueOnGameThread(), HeroNear + 1.f);
	const FVector HeroAt = King->GetActorLocation();
	// Zoomed far out, a team-coloured pip over each troop so armies read at a glance: it fades in from 75 m of camera
	// distance to full at 110 m, by when a voxel troop is only a few pixels tall.
	const FVector Eye = PCtrl->PlayerCameraManager->GetCameraLocation();
	const float S = FMath::Max(2.f, U(4.f));
	// (B: the frame's one list of the living with each one's platoon; a pip's rows go into the canvas batch directly,
	// the same rectangles as before)
	const bool bFast = CVarOptHud.GetValueOnGameThread() != 0;
	const FUnitFrame& Frame = UnitsThisFrame();
	static const IConsoleVariable* PipTris = IConsoleManager::Get().FindConsoleVariable(TEXT("vl.Opt.PipTris"));
	const bool bPipTris = !PipTris || PipTris->GetInt() != 0;
	BeginRects();
	for (AVLKing* Unit : Frame.Live)
	{
		// (a tower's own archer never leaves its lookout: no diamond, as it has no outline through walls)
		if (Unit->IsDead() || Unit->bTowerGuard || (bHero && Unit->Team != UVLBattle::Enemy))
		{
			continue;
		}
		const float Alpha = bHero ? FMath::GetMappedRangeValueClamped(FVector2f(HeroNear, HeroFull), FVector2f(0.f, 1.f), float(FVector::Dist(HeroAt, Unit->GetActorLocation())))
			: FMath::GetMappedRangeValueClamped(FVector2f(7500.f, 11000.f), FVector2f(0.f, 1.f), float(FVector::Dist(Eye, Unit->GetActorLocation())));
		if (Alpha <= 0.01f)
		{
			continue;
		}
		const FVector P = Project(Unit->GetActorLocation() + FVector(0.f, 0.f, 140.f));
		if (P.Z <= 0.f)
		{
			continue;
		}
		const FLinearColor Team = UVLBattle::TeamColour(Unit->Team);
		FLinearColor Col = FLinearColor(FMath::Min(Team.R * 1.6f + 0.15f, 1.f), FMath::Min(Team.G * 1.6f + 0.15f, 1.f), FMath::Min(Team.B * 1.6f + 0.15f, 1.f), Alpha);
		// a platoon's troops show in its colour from afar too; the player's units in no platoon are grey
		if (Command && Unit->Team == UVLBattle::Player)
		{
			Col = FLinearColor(0.62f, 0.63f, 0.66f, Alpha);
			if (bFast)
			{
				if (const int32* In = Frame.Platoon.Find(Unit)) { Col = PlatoonColor(*In); Col.A = Alpha; }
			}
			else
			{
				for (int32 i = 0; i < UVLCommand::MaxPlatoons; ++i)
				{
					TArray<AVLKing*> Members;
					Command->GetPlatoon(i, Members);
					if (Members.Contains(Unit)) { Col = PlatoonColor(i); Col.A = Alpha; break; }
				}
			}
		}
		const bool bSel = Command && (bFast ? Frame.Selected.Contains(Unit) : Command->IsSelected(Unit));
		// a little diamond with a dark rim
		for (int32 r = 0; r < 2; ++r)
		{
			const float H = S + (r == 0 ? FMath::Max(1.f, U(1.5f)) : 0.f);
			const FLinearColor C = r == 0 ? FLinearColor(0.02f, 0.02f, 0.03f, Alpha * 0.85f) : (bSel ? FLinearColor(1.f, 0.95f, 0.7f, Alpha) : Col);
			if (!(C.A > 0.f))
			{
				continue;
			}
			const FLinearColor CL = Lin(C);     // (once for the diamond's rows)
			if (RectBatch && bPipTris)
			{
				// (Windows pass, batch 1) the diamond as two triangles instead of a row of the canvas for each of its
				// lines: the same four corners (the rows ran from H above to H below the point, a pixel tall each)
				FLinearColor Actual = CL;
				Actual.A *= Canvas->Canvas->AlphaModulate;
				const FHitProxyId HitProxyId = Canvas->Canvas->GetHitProxyId();
				const float Cx = FMath::RoundToFloat(P.X), Cy = float(P.Y) + 0.5f, R = H + 0.5f;
				const int32 VL = RectBatch->AddVertexf(FVector4f(Cx - R, Cy, 0.f, 1.f), FVector2f(0.f, 0.5f), Actual, HitProxyId);
				const int32 VT = RectBatch->AddVertexf(FVector4f(Cx, Cy - R, 0.f, 1.f), FVector2f(0.5f, 0.f), Actual, HitProxyId);
				const int32 VR = RectBatch->AddVertexf(FVector4f(Cx + R, Cy, 0.f, 1.f), FVector2f(1.f, 0.5f), Actual, HitProxyId);
				const int32 VB = RectBatch->AddVertexf(FVector4f(Cx, Cy + R, 0.f, 1.f), FVector2f(0.5f, 1.f), Actual, HitProxyId);
				RectBatch->AddTriangleExtensive(VL, VT, VR, nullptr, GWhiteTexture, SE_BLEND_Translucent);
				RectBatch->AddTriangleExtensive(VL, VR, VB, nullptr, GWhiteTexture, SE_BLEND_Translucent);
				continue;
			}
			for (float dy = -H; dy <= H; dy += 1.f)
			{
				const float w = H - FMath::Abs(dy);
				RectLinear(FMath::RoundToFloat(P.X - w), FMath::RoundToFloat(P.Y + dy), FMath::Max(1.f, 2.f * w), 1.f, CL);
			}
		}
	}
	EndRects();
}

void AVLHUD::DrawRangeCircles()
{
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!Battle || !King || King->IsHeroMode() || Battle->GetState() == EVLMatch::Idle)
	{
		RangeCircles.Reset();
		return;
	}
	const float W = FMath::Max(1.f, U(2.f));

	// A tower's (or the castle's) reach: the selected one's, from its walls (as UVLBattle measures it).
	{
		AActor* B = SelectedBuilding();
		const FVLBuildingState* St = B ? Battle->FindBuilding(B) : nullptr;
		const float Reach = (St && (St->Kind == EVLBuilding::Tower || St->Kind == EVLBuilding::Castle)) ? VLRules::Level(St->Kind, St->Level).Range : 0.f;
		const UStaticMeshComponent* SMC = B ? B->FindComponentByClass<UStaticMeshComponent>() : nullptr;
		if (Reach > 0.f && SMC && SMC->GetStaticMesh())
		{
			if (BuildingReachOf.Get() != B || !FMath::IsNearlyEqual(BuildingReach.ReachRadius, Reach) || BuildingReach.Sight.Num() == 0)
			{
				BuildingReachOf = B;
				BuildingReach.ReachRadius = Reach;
				BuildingReach.Sight.Reset();
				// the box grown by the reach (a rounded rectangle): for each direction, the box's corner furthest that
				// way, pushed out along it
				const FTransform T = SMC->GetComponentTransform();
				const FBox Box = SMC->GetStaticMesh()->GetBoundingBox();
				const float RefZ = B->GetActorLocation().Z;
				const int32 N = 96;
				for (int32 i = 0; i < N; ++i)
				{
					const float Ang = 2.f * PI * i / N;
					const FVector Dir(FMath::Cos(Ang), FMath::Sin(Ang), 0.f);
					const FVector Local = T.InverseTransformVectorNoScale(Dir);
					const FVector Corner = T.TransformPosition(FVector(Local.X >= 0.f ? Box.Max.X : Box.Min.X, Local.Y >= 0.f ? Box.Max.Y : Box.Min.Y, Box.Min.Z));
					const FVector2D P = FVector2D(Corner) + FVector2D(Dir) * Reach;
					BuildingReach.Sight.Add(FVector(P.X, P.Y, GroundZ(P, RefZ) + 15.f));
				}
			}
			const FLinearColor Color = St->Team == UVLBattle::Enemy ? FLinearColor(1.f, 0.3f, 0.25f, 0.9f) : RangeCircle;
			const int32 N = BuildingReach.Sight.Num();
			for (int32 i = 0; i < N; ++i)
			{
				const FVector S0 = Project(BuildingReach.Sight[i]);
				const FVector S1 = Project(BuildingReach.Sight[(i + 1) % N]);
				if (S0.Z > 0.f && S1.Z > 0.f) { DrawLine(S0.X, S0.Y, S1.X, S1.Y, Color, FMath::Max(1.f, U(2.5f))); }
			}
			// what the player's tower sees (the fog of war's outline, dashed: its reach x vl.Fog.TowerView and the ground's lie)
			TArray<FVector> TowerView;
			if (St->Team == UVLBattle::Player && UVLFog::Get(this) && UVLFog::Get(this)->Outline(B, TowerView))
			{
				for (int32 i = 0; i < TowerView.Num(); i += 2)
				{
					const FVector S0 = Project(TowerView[i]), S1 = Project(TowerView[(i + 1) % TowerView.Num()]);
					if (S0.Z > 0.f && S1.Z > 0.f) { DrawLine(S0.X, S0.Y, S1.X, S1.Y, SightCircle, FMath::Max(1.f, U(2.f))); }
				}
			}
		}
		else
		{
			BuildingReachOf = nullptr;
			BuildingReach.Sight.Reset();
		}
	}

	// The selected troops nearest the middle of the selection (a big blob of circles reads as nothing).
	TArray<AVLKing*> Units;
	SelectedUnits(Units);
	FVector2D Mid = FVector2D::ZeroVector;
	for (const AVLKing* Un : Units) { Mid += FVector2D(Un->GetActorLocation()); }
	for (auto It = RangeCircles.CreateIterator(); It; ++It) { if (!It.Key().IsValid() || !Units.Contains(It.Key().Get())) { It.RemoveCurrent(); } }
	if (Units.Num() == 0)
	{
		return;
	}
	Mid /= Units.Num();
	Units.Sort([&Mid](const AVLKing& A, const AVLKing& B) { return FVector2D::DistSquared(FVector2D(A.GetActorLocation()), Mid) < FVector2D::DistSquared(FVector2D(B.GetActorLocation()), Mid); });
	if (Units.Num() > 12) { Units.SetNum(12); }

	// Points hug the ground; they are re-sampled only once the troop has moved a little.
	auto MakeRing = [this](const FVector2D& C, float R, float RefZ, TArray<FVector>& Out)
	{
		const int32 N = FMath::Clamp(FMath::RoundToInt(R / 30.f), 40, 80);
		Out.Reset(N);
		for (int32 i = 0; i < N; ++i)
		{
			const float Ang = 2.f * PI * i / N;
			const FVector2D P = C + FVector2D(FMath::Cos(Ang), FMath::Sin(Ang)) * R;
			Out.Add(FVector(P.X, P.Y, GroundZ(P, RefZ) + 15.f));
		}
	};
	auto Reach = [](AVLKing* U) -> float
	{
		if (!U->IsRanged()) { return 0.f; }
		const UVLArcherCombat* Bow = UVLArcherCombat::For(U, false);
		const UVLArcherCombat* Def = GetDefault<UVLArcherCombat>();
		return U->IsGarrisoned() ? (Bow ? Bow->TowerRange : Def->TowerRange) : (Bow ? Bow->Range : Def->Range);
	};
	auto Sight = [](const AVLKing* U) { const VLRules::FTroop& T = VLRules::Troop(U->GetKind()); return U->IsGarrisoned() ? GetDefault<UVLArcherCombat>()->TowerRange : FMath::Max(T.Acquire, T.Sight); };   // (the Spy: no acquire range, a long sight)
	// Several troops' circles merge into one outline: a stretch inside another troop's circle of the same kind is skipped.
	struct FDisc { FVector2D C; float R; };
	TArray<FDisc> SightDiscs, ReachDiscs;
	for (AVLKing* Un : Units)
	{
		const float FogR = UVLFog::Get(this) ? UVLFog::Get(this)->ViewRadius(Un) : 0.f;
		SightDiscs.Add({ FVector2D(Un->GetActorLocation()), FogR > 0.f ? FogR : Sight(Un) });
		if (Reach(Un) > 0.f) { ReachDiscs.Add({ FVector2D(Un->GetActorLocation()), Reach(Un) }); }
	}
	auto Covered = [](const TArray<FDisc>& Discs, const FVector2D& P, const FVector2D& Own)
	{
		for (const FDisc& D : Discs)
		{
			if (D.C.Equals(Own, 1.f)) { continue; }
			if (FVector2D::DistSquared(D.C, P) < FMath::Square(D.R - 4.f)) { return true; }
		}
		return false;
	};
	auto Draw = [&](const TArray<FVector>& Pts, const FVector2D& Own, const TArray<FDisc>& Discs, const FLinearColor& Color, bool bDashed)
	{
		const int32 N = Pts.Num();
		for (int32 i = 0; i < N; ++i)
		{
			if (bDashed && (i & 1)) { continue; }
			const FVector M = (Pts[i] + Pts[(i + 1) % N]) * 0.5f;
			if (Covered(Discs, FVector2D(M.X, M.Y), Own)) { continue; }
			const FVector S0 = Project(Pts[i]);
			const FVector S1 = Project(Pts[(i + 1) % N]);
			if (S0.Z <= 0.f || S1.Z <= 0.f) { continue; }
			DrawLine(S0.X, S0.Y, S1.X, S1.Y, Color, W);
		}
	};
	for (AVLKing* Un : Units)
	{
		FRangeCircle& C = RangeCircles.FindOrAdd(Un);
		const FVector2D P(Un->GetActorLocation());
		const float R = Reach(Un);
		if (FVector2D::DistSquared(P, C.At) > FMath::Square(80.f) || !FMath::IsNearlyEqual(C.ReachRadius, R))
		{
			C.At = P;
			C.ReachRadius = R;
			if (UVLFog* Fog = UVLFog::Get(this); !Fog || !Fog->Outline(Un, C.Sight)) { MakeRing(P, Sight(Un), Un->GetFeet().Z, C.Sight); }    // (the fog of war on: what it sees)
			if (R > 0.f) { MakeRing(P, R, Un->GetFeet().Z, C.Reach); } else { C.Reach.Reset(); }
		}
		const bool bEnemy = Un->Team == UVLBattle::Enemy;
		Draw(C.Sight, P, SightDiscs, bEnemy ? FLinearColor(1.f, 0.4f, 0.35f, 0.45f) : SightCircle, true);
		if (C.Reach.Num() > 0) { Draw(C.Reach, P, ReachDiscs, RangeCircle, false); }
	}
}

void AVLHUD::DrawRouteLines()
{
	// Dashed ground lines: the pathway of the selected troops (blue), their patrol (orange) or attack-move (red), and a
	// selected barracks' or range's rally point.
	LineStats = FLineStats();
	const UVLBattle* Battle = UVLBattle::Get(this);
	const UVLCommand* Command = UVLCommand::Get(this);
	if (!Battle || !Command || !King)
	{
		return;
	}
	if (King->IsHeroMode())
	{
		// the hero view: no pathways, follow, patrol or queue lines (troops following the hero, as their platoon's
		// leader or the unit they were sent after, would trail lines across the view); the order markers still show
		// where an order from the crosshair went. Back in the overview.
		LineStats.bHidden = true;
		return;
	}
	auto Dashed = [this](const FVector& A0, const FVector& B0, const FLinearColor& Color, bool bEnds, float Width = 2.f)
	{
		const FVector Lift(0.f, 0.f, 20.f);
		const int32 N = FMath::Clamp(int32(FVector::Dist(A0, B0) / 60.f) * 2, 2, 64);
		++LineStats.Segments;
		for (int32 i = 0; i < N; i += 2)
		{
			const FVector S0 = Project(FMath::Lerp(A0, B0, float(i) / N) + Lift);
			const FVector S1 = Project(FMath::Lerp(A0, B0, float(i + 1) / N) + Lift);
			if (S0.Z <= 0.f || S1.Z <= 0.f) { continue; }
			DrawLine(S0.X, S0.Y, S1.X, S1.Y, Color, FMath::Max(1.f, U(Width)));
		}
		if (bEnds)
		{
			const FVector S = Project(B0 + Lift);
			if (S.Z > 0.f) { Fill(S.X - U(4.f), S.Y - U(4.f), U(8.f), U(8.f), Color); }
		}
	};
	const FLinearColor Blue(0.55f, 0.8f, 1.f, 0.85f);
	TArray<AVLKing*> Units;
	Command->GetSelection(Units);
	// each patrol or attack-move once (a group shares one): a patrol's whole loop in orange, an attack-move's points
	// still to reach in blue (the main game's route lines)
	{
		const FLinearColor Orange(1.f, 0.62f, 0.25f, 0.85f);
		auto Ground = [this](const FVector& P) { return FVector(P.X, P.Y, GroundZ(FVector2D(P), P.Z)); };
		TArray<int32> Drawn;
		for (AVLKing* Un : Units)
		{
			TArray<FVector> Points;
			bool bLoop = false;
			int32 Next = 0, Id = 0;
			if (!Command->GetRoute(Un, Points, bLoop, Next, &Id) || Points.Num() == 0 || Drawn.Contains(Id))
			{
				continue;
			}
			Drawn.Add(Id);
			if (bLoop)
			{
				for (int32 k = 0; k < Points.Num(); ++k)
				{
					if (Points.Num() == 2 && k == 1)
					{
						break;      // two points: one line, walked both ways
					}
					Dashed(Ground(Points[k]), Ground(Points[(k + 1) % Points.Num()]), Orange, true);
				}
				const FVector S = Project(Ground(Points[0]) + FVector(0.f, 0.f, 20.f));
				if (S.Z > 0.f) { Fill(S.X - U(4.f), S.Y - U(4.f), U(8.f), U(8.f), Orange); }
			}
			else
			{
				FVector From = Ground(Un->GetFeet());
				for (int32 k = FMath::Clamp(Next, 0, Points.Num() - 1); k < Points.Num(); ++k)
				{
					Dashed(From, Ground(Points[k]), FLinearColor(1.f, 0.42f, 0.32f, 0.85f), true);
					From = Ground(Points[k]);
				}
			}
		}
	}
	// The pathways. Each walker's own, unless it walks in a big group: a platoon's members on the way, or (in no
	// platoon) those of one group order (one march, AVLKing::MarchId; else those heading for the same place). A group
	// of more than vl.RouteLines.GroupOver (7) draws ONE line, its leader's (a platoon's leader if he walks with them,
	// else whoever is nearest their middle), a little heavier: thirty lines side by side said nothing more.
	{
		struct FWalker { AVLKing* Unit = nullptr; TArray<FVector> Route, Legs; int32 Group = INDEX_NONE; };
		TArray<FWalker> Walkers;
		for (AVLKing* Un : Units)
		{
			FWalker W;
			W.Unit = Un;
			Un->GetPathway(W.Route, W.Legs);
			TArray<FVector> RoutePoints;
			bool bRouteLoop = false;
			int32 RouteNext = 0;
			if (W.Legs.Num() == 0 || Command->GetRoute(Un, RoutePoints, bRouteLoop, RouteNext))
			{
				continue;               // (a patrol's or attack-move's leg: its route is drawn above)
			}
			if (const UVLBuilderWork* Work = UVLBuilderWork::For(Un, false); Work && (Work->GetJob() || Work->HasTasks()))
			{
				continue;               // (a Builder on a job or with a queue: its chain below draws its way)
			}
			Walkers.Add(MoveTemp(W));
		}
		// groups: walkers of one group order (one march), of one platoon, or (neither) heading for the same place, are
		// one group; and so are two groups that share a walker's march or platoon (a selection of a platoon and some
		// loose troops sent together is one group)
		const FUnitFrame& Frame = UnitsThisFrame();
		TArray<int32> Platoons;
		for (FWalker& W : Walkers)
		{
			const int32* InPlatoon = Frame.Platoon.Find(W.Unit);
			Platoons.Add(InPlatoon ? *InPlatoon : INDEX_NONE);
		}
		int32 NumGroups = 0;
		for (int32 i = 0; i < Walkers.Num(); ++i)
		{
			FWalker& W = Walkers[i];
			for (int32 j = 0; j < i; ++j)
			{
				const FWalker& O = Walkers[j];
				const bool bSame = (W.Unit->MarchId != 0 && W.Unit->MarchId == O.Unit->MarchId) || (Platoons[i] != INDEX_NONE && Platoons[i] == Platoons[j])
					|| (W.Unit->MarchId == 0 && O.Unit->MarchId == 0 && Platoons[i] == INDEX_NONE && Platoons[j] == INDEX_NONE && FVector::DistSquared2D(W.Legs.Last(), O.Legs.Last()) < FMath::Square(2500.f));
				if (!bSame || W.Group == O.Group)
				{
					continue;
				}
				if (W.Group == INDEX_NONE)
				{
					W.Group = O.Group;
				}
				else
				{
					const int32 From = O.Group, To = W.Group;       // (two groups it joins: one now)
					for (int32 k = 0; k < i; ++k) { if (Walkers[k].Group == From) { Walkers[k].Group = To; } }
				}
			}
			if (W.Group == INDEX_NONE)
			{
				W.Group = NumGroups++;
			}
		}
		struct FGroup { TArray<int32> Members; };
		TArray<FGroup> Groups;
		Groups.SetNum(NumGroups);
		for (int32 i = 0; i < Walkers.Num(); ++i) { Groups[Walkers[i].Group].Members.Add(i); }
		auto DrawWay = [&](const FWalker& W, float Width)
		{
			// from the troop along the route it is walking to the point it is heading for, then the legs after it
			FVector From = W.Unit->GetFeet();
			for (const FVector& P : W.Route) { Dashed(From, P, Blue, false, Width); From = P; }
			Dashed(From, W.Legs[0], Blue, true, Width);
			for (int32 k = 1; k < W.Legs.Num(); ++k) { Dashed(W.Legs[k - 1], W.Legs[k], Blue, true, Width); }
			++LineStats.Pathways;
		};
		const int32 GroupOver = FMath::Max(CVarRouteGroup.GetValueOnGameThread(), 1);
		for (const FGroup& G : Groups)
		{
			if (G.Members.Num() == 0)
			{
				continue;               // (a group merged into another)
			}
			if (G.Members.Num() <= GroupOver)
			{
				for (const int32 i : G.Members) { DrawWay(Walkers[i], 2.f); }
				continue;
			}
			// its line: a platoon's leader walking with them, else whoever is nearest their middle
			FVector Mid = FVector::ZeroVector;
			for (const int32 i : G.Members) { Mid += Walkers[i].Unit->GetFeet() / G.Members.Num(); }
			int32 Pick = G.Members[0];
			float Best = TNumericLimits<float>::Max();
			for (const int32 i : G.Members)
			{
				const bool bLeads = Platoons[i] != INDEX_NONE && Command->GetPlatoonLeader(Platoons[i]) == Walkers[i].Unit;
				const float D = bLeads ? -1.f : float(FVector::DistSquared2D(Walkers[i].Unit->GetFeet(), Mid));
				if (D < Best) { Best = D; Pick = i; }
			}
			DrawWay(Walkers[Pick], 3.f);
			++LineStats.Grouped;
		}
	}
	// a Builder's queue (Shift orders): a numbered chain from the Builder through what it is on now (1: the building it
	// works on, or the walk it is on) and then each order of its queue in turn (2, 3, ...), walks blue and buildings
	// gold; an order that has lapsed (the site cancelled or fallen) is left out. A crew sharing one queue draws the
	// chain once, each Builder its own line to the first. While placing with Shift held (and Builders selected), a pale
	// segment from the end of the chain to the ghost, with the number the site would get.
	{
		const FLinearColor Work(1.f, 0.82f, 0.3f, 0.95f);
		const FLinearColor WalkCol(0.55f, 0.8f, 1.f, 0.95f);
		auto Ground = [this](const FVector& P) { return FVector(P.X, P.Y, GroundZ(FVector2D(P), P.Z)); };
		struct FItem { FVector At = FVector::ZeroVector; bool bMove = false; const AActor* Building = nullptr; };
		struct FBadge { FVector At; int32 N; FLinearColor Col; };
		TArray<TArray<FItem>> Chains;
		TArray<FBadge> Badges;
		TArray<FItem> First;            // the first selected Builder's chain (the Shift preview goes on from its end)
		const AVLKing* FirstBuilder = nullptr;
		auto Same = [](const FItem& A0, const FItem& B0)
		{
			return A0.bMove == B0.bMove && (A0.bMove ? FVector::Dist2D(A0.At, B0.At) < 450.f : A0.Building == B0.Building);
		};
		for (AVLKing* Un : Units)
		{
			if (!UVLBuilderWork::IsBuilder(Un) || !Un->IsAlive())
			{
				continue;
			}
			if (!FirstBuilder)
			{
				FirstBuilder = Un;
			}
			const UVLBuilderWork* W = UVLBuilderWork::For(Un, false);
			if (!W || (!W->GetJob() && !W->HasTasks()))
			{
				continue;
			}
			TArray<FItem> Items;
			if (const AActor* Job = W->GetJob())
			{
				Items.Add({ Ground(Job->GetActorLocation()), false, Job });
			}
			else if (Un->HasOrder() && Un->GetWaypoints().Num() > 0)
			{
				Items.Add({ Ground(Un->GetWaypoints().Last()), true, nullptr });       // (the queued walk it is on)
			}
			for (const UVLBuilderWork::FTask& T : W->GetTasks())
			{
				if (T.bMove)
				{
					Items.Add({ Ground(T.Point), true, nullptr });
				}
				else if (const AActor* B = T.Building.Get())
				{
					Items.Add({ Ground(B->GetActorLocation()), false, B });
				}
			}
			if (Items.Num() == 0)
			{
				continue;
			}
			if (Un == FirstBuilder)
			{
				First = Items;
			}
			// its own line to the first: along the route it is walking now
			const FLinearColor C0 = Items[0].bMove ? WalkCol : Work;
			FVector From = Ground(Un->GetFeet());
			if (Un->HasOrder())
			{
				for (const FVector& P : Un->GetWaypoints()) { Dashed(From, P, C0, false, 3.f); From = P; }
			}
			Dashed(From, Items[0].At, C0, true, 3.f);
			// the chain, once per crew
			if (Chains.ContainsByPredicate([&](const TArray<FItem>& C)
				{
					if (C.Num() != Items.Num()) { return false; }
					for (int32 k = 0; k < C.Num(); ++k) { if (!Same(C[k], Items[k])) { return false; } }
					return true;
				}))
			{
				continue;
			}
			Chains.Add(Items);
			for (int32 k = 0; k < Items.Num(); ++k)
			{
				const FLinearColor C = Items[k].bMove ? WalkCol : Work;
				if (k > 0)
				{
					Dashed(Items[k - 1].At, Items[k].At, C, true, 3.f);
				}
				Badges.Add({ Items[k].At, k + 1, C });
			}
		}
		// Shift held while placing: where the next site goes in the order
		const UVLConstruction* Construction = UVLConstruction::Get(this);
		const bool bShiftHeld = PCtrl && (PCtrl->IsInputKeyDown(EKeys::LeftShift) || PCtrl->IsInputKeyDown(EKeys::RightShift));
		if (FirstBuilder && bShiftHeld && Construction && Construction->IsPlacing() && Construction->HasPlacementUnderPointer())
		{
			const FVLPlacement& P = Construction->GetPlacement();
			const float Pulse = 0.5f + 0.5f * FMath::Sin(float(Now) * 5.f);
			const FLinearColor C = P.bValid ? FLinearColor(1.f, 0.93f, 0.7f, 0.55f + 0.3f * Pulse) : FLinearColor(1.f, 0.35f, 0.3f, 0.5f + 0.25f * Pulse);
			const FVector From = First.Num() > 0 ? First.Last().At : Ground(FirstBuilder->GetFeet());
			Dashed(From, Ground(P.Location), C, true, 2.f);
			Badges.Add({ Ground(P.Location), First.Num() + 1, C });
			LineStats.bPreview = true;
		}
		// the numbers last, over the lines: a dark plate edged in the order's colour, on a stalk to its point
		for (const FBadge& B : Badges)
		{
			const FVector S = Project(B.At + FVector(0.f, 0.f, 20.f));
			if (S.Z <= 0.f)
			{
				continue;
			}
			const FString Num = FString::FromInt(B.N);
			const float R = U(10.f), E = FMath::Max(1.f, U(2.f));
			const float BW = FMath::Max(2.f * R, TextSize(Num, U(14.f), Bold).X + U(8.f));
			const float BX = FMath::RoundToFloat(S.X - BW * 0.5f), BY = FMath::RoundToFloat(S.Y - 2.f * R - U(18.f));
			DrawLine(S.X, BY + 2.f * R, S.X, S.Y, B.Col, FMath::Max(1.f, U(1.5f)));
			Fill(BX - E, BY - E, BW + 2.f * E, 2.f * R + 2.f * E, B.Col);
			Fill(BX, BY, BW, 2.f * R, FLinearColor(0.02f, 0.03f, 0.06f, 0.92f));
			TextIn(FBox2D(FVector2D(BX, BY), FVector2D(BX + BW, BY + 2.f * R)), Num, U(14.f), B.Col, AlignCentre, Bold);
		}
		LineStats.Badges = Badges.Num();
		LineStats.Chains = Chains.Num();
	}
	// (a barracks' / range's only when one was set: without one its recruits wait in its yard)
	if (const FVLBuildingState* St = Battle->FindBuilding(SelectedBuilding()); St && St->Trains() && St->Team == UVLBattle::Player && (St->bHasRally || St->Kind == EVLBuilding::Castle))
	{
		FVector Door, Rally, Front;
		Battle->FrontOf(St->Actor.Get(), Door, Rally, Front);
		const FVector To = St->bHasRally ? St->Rally : Rally;
		Dashed(FVector(Door.X, Door.Y, GroundZ(FVector2D(Door), Door.Z)), FVector(To.X, To.Y, GroundZ(FVector2D(To), To.Z)), Blue, true);
	}
}

void AVLHUD::DrawOrderChains()
{
	LineStats.OrderChains = LineStats.OrderBadges = 0;
	const UVLCommand* Command = UVLCommand::Get(this);
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!Command || !Battle || !King)
	{
		return;
	}
	TArray<UVLCommand::FChainView> Chains;
	Command->GetChains(Chains);
	if (Chains.Num() == 0)
	{
		return;
	}
	const bool bHero = King->IsHeroMode();
	TSet<const AVLKing*> Shown;
	Command->GetSelectionSet(Shown);
	if (bHero)
	{
		TArray<AVLKing*> Commanded;
		King->HeroCommanded(Commanded);
		Shown.Append(Commanded);
	}
	const FLinearColor AttackCol(1.f, 0.42f, 0.32f, 0.95f), WalkCol(0.55f, 0.8f, 1.f, 0.95f);
	auto Ground = [this](const FVector& P) { return FVector(P.X, P.Y, GroundZ(FVector2D(P), P.Z)); };
	auto Dashed = [this](const FVector& A0, const FVector& B0, const FLinearColor& Color)
	{
		const FVector Lift(0.f, 0.f, 20.f);
		const int32 N = FMath::Clamp(int32(FVector::Dist(A0, B0) / 60.f) * 2, 2, 64);
		for (int32 i = 0; i < N; i += 2)
		{
			const FVector S0 = Project(FMath::Lerp(A0, B0, float(i) / N) + Lift);
			const FVector S1 = Project(FMath::Lerp(A0, B0, float(i + 1) / N) + Lift);
			if (S0.Z <= 0.f || S1.Z <= 0.f) { continue; }
			DrawLine(S0.X, S0.Y, S1.X, S1.Y, Color, FMath::Max(1.f, U(2.f)));
		}
	};
	for (const UVLCommand::FChainView& C : Chains)
	{
		if (C.Members.Num() == 0 || !(C.Members.ContainsByPredicate([&Shown](const AVLKing* M) { return Shown.Contains(M); }) || (bHero && C.Rejoin == King)))
		{
			continue;
		}
		++LineStats.OrderChains;
		// where each item is: a foe over its head (a building over its middle), a walk on the ground
		FVector From = FVector::ZeroVector;
		for (const AVLKing* M : C.Members) { From += M->GetFeet(); }
		From = Ground(From / C.Members.Num());
		int32 N = 0;
		for (const UVLCommand::FChainItem& It : C.Items)
		{
			FVector On = It.Ground, Over = It.Ground;
			if (It.bAttack)
			{
				const AActor* T = It.Target.Get();
				if (!T || !Battle->IsAlive(T))
				{
					continue;           // (fallen meanwhile: passed over)
				}
				if (const AVLKing* TU = Cast<AVLKing>(T))
				{
					On = TU->GetFeet();
					Over = TU->GetActorLocation() + FVector(0.f, 0.f, 150.f);
				}
				else
				{
					FVector Origin, Extent;
					T->GetActorBounds(true, Origin, Extent);
					On = FVector(Origin.X, Origin.Y, T->GetActorLocation().Z);
					Over = Origin + FVector(0.f, 0.f, Extent.Z * 0.6f);
				}
			}
			else
			{
				On = Over = Ground(It.Ground);
			}
			++N;
			const FLinearColor Col = It.bAttack ? AttackCol : WalkCol;
			if (!bHero)
			{
				Dashed(From, Ground(On), Col);      // (the hero view keeps no lines across it: only the numbers)
				From = Ground(On);
			}
			const FVector S = Project(Over + FVector(0.f, 0.f, 20.f));
			if (S.Z <= 0.f || S.X < -40.f || S.Y < -40.f || S.X > View.X + 40.f || S.Y > View.Y + 40.f)
			{
				continue;
			}
			// a dark plate edged in the item's colour (the Builders' queue's), smaller in the hero view; the one under
			// way pulses
			const FString Num = FString::FromInt(N);
			const float R = U(bHero ? 8.f : 10.f), E = FMath::Max(1.f, U(2.f));
			const float BW = FMath::Max(2.f * R, TextSize(Num, U(bHero ? 12.f : 14.f), Bold).X + U(8.f));
			const float BX = FMath::RoundToFloat(S.X - BW * 0.5f), BY = FMath::RoundToFloat(S.Y - 2.f * R - U(bHero ? 6.f : 18.f));
			const bool bNow = N == 1 && C.bStarted;
			const FLinearColor Edge = bNow ? FMath::Lerp(Col, FLinearColor::White, 0.35f + 0.35f * FMath::Sin(float(Now) * 6.f)) : Col;
			if (!bHero)
			{
				DrawLine(S.X, BY + 2.f * R, S.X, S.Y, Col, FMath::Max(1.f, U(1.5f)));
			}
			Fill(BX - E, BY - E, BW + 2.f * E, 2.f * R + 2.f * E, Edge);
			Fill(BX, BY, BW, 2.f * R, FLinearColor(0.02f, 0.03f, 0.06f, 0.92f));
			TextIn(FBox2D(FVector2D(BX, BY), FVector2D(BX + BW, BY + 2.f * R)), Num, U(bHero ? 12.f : 14.f), Col, AlignCentre, Bold);
			++LineStats.OrderBadges;
		}
	}
}

void AVLHUD::DrawOrderMarkers()
{
	// where the last orders went: a ring closing on the spot
	const UVLCommand* Command = UVLCommand::Get(this);
	if (!Command || !King)
	{
		return;         // (the hero view's orders show theirs too)
	}
	for (const UVLCommand::FMarker& M : Command->GetMarkers())
	{
		const float T = float(Now - M.Time) / UVLCommand::MarkerSeconds;
		if (T >= 0.f && T < 1.f)
		{
			const FLinearColor C(SelectionRing.R, SelectionRing.G, SelectionRing.B, 1.f - T * 0.6f);
			Ring(M.At + FVector(0.f, 0.f, 8.f), FMath::Lerp(150.f, 35.f, FMath::Sqrt(T)), C, FMath::Max(1.f, U(3.f)));
			Ring(M.At + FVector(0.f, 0.f, 8.f), 22.f, C, FMath::Max(1.f, U(2.f)));
		}
	}
}

void AVLHUD::DrawTrainingBars()
{
	// A building at work shows its progress over the roof even when nothing is selected: training (below) and, for
	// your own buildings, a level being raised. Several stack upward.
	const UVLBattle* Battle = UVLBattle::Get(this);
	if (!Battle || Battle->GetState() == EVLMatch::Idle)
	{
		return;
	}
	for (const FVLBuildingState& B : Battle->GetBuildings())
	{
		if (!B.IsAlive() || B.Team != UVLBattle::Player || B.UpgradeLeft < 0.f)
		{
			continue;
		}
		const FVector S = Project(LabelPoint(B.Actor.Get()));
		if (S.Z <= 0.f)
		{
			continue;
		}
		const float W = U(110.f), H = U(9.f), IS = U(24.f), Step = U(26.f);
		// above the training bar when the building is also training
		const float X = FMath::RoundToFloat(S.X - W * 0.5f + IS * 0.5f), Y = FMath::RoundToFloat(S.Y - (B.Queue.Num() > 0 ? Step : 0.f));
		Icon(EVLIcon::Crown, X - IS - U(5.f), Y + H * 0.5f - IS * 0.5f, IS);
		Meter(X, Y, W, H, 1.f - B.UpgradeLeft / FMath::Max(B.UpgradeTotal, 0.1f), GoldBright);
		Text(FString::Printf(TEXT("level %d  %s"), B.Level + 1, *Countdown(B.UpgradeLeft)), X + W + U(6.f), Y - U(5.f), U(14.f), Parchment, AlignLeft, Bold);
	}
	for (const FVLBuildingState& B : Battle->GetBuildings())
	{
		if (!B.IsAlive() || B.Queue.Num() == 0 || !UVLFog::InSight(B.Actor.Get()))      // (an enemy's in the fog of war: not shown)
		{
			continue;
		}
		const FVector S = Project(LabelPoint(B.Actor.Get()));
		if (S.Z <= 0.f)
		{
			continue;
		}
		const bool bEnemy = B.Team == UVLBattle::Enemy;
		const float W = U(110.f), H = U(9.f), IS = U(26.f);
		const float X = FMath::RoundToFloat(S.X - W * 0.5f + IS * 0.5f), Y = FMath::RoundToFloat(S.Y);
		Portrait(VLPortraitOf(B.Queue[0]), X - IS - U(5.f), Y + H * 0.5f - IS * 0.5f, IS, FLinearColor::White, bEnemy);
		Meter(X, Y, W, H, Battle->TrainProgress(B.Actor.Get()), GoldBright);
		if (B.Queue.Num() > 1)
		{
			Text(FString::Printf(TEXT("x%d"), B.Queue.Num()), X + W + U(6.f), Y - U(6.f), U(16.f), Parchment, AlignLeft, Bold);
		}
	}
}
