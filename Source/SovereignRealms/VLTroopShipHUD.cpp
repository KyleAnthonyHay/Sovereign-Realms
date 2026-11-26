// The troop ship in the interface (AVLHUD::DrawShipPanel): a plate over each of the player's ships that says who is
// aboard, the dock button over a berth in its reach, a selected ship's course (the troops' dashed lines: blue for a
// course and its queued points, orange for a patrol's loop), and the selection panel of a selected ship with its
// Dock and Unload buttons. The ship itself: VLTroopShip.*.
#include "VLHUD.h"

#include "SovereignRealms.h"
#include "VLBattle.h"
#include "VLCommand.h"
#include "VLGameMode.h"
#include "VLHUDStyle.h"
#include "VLKing.h"
#include "VLTroopShip.h"
#include "VLTroopShipDeck.inl"

#include "GameFramework/PlayerController.h"

using namespace VLStyle;

bool AVLHUD::DrawShipPanel(float X, float Bottom, float Room)
{
	const UVLFleet* Fleet = UVLFleet::Get(this);
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Fleet || !Command || !King || !PCtrl || Fleet->GetShips().Num() == 0)
	{
		return false;
	}
	AVLTroopShip* Sel = Cast<AVLTroopShip>(King->GetSelected());
	// over each of the player's ships with anyone aboard or coming (and the selected one): how many it carries
	for (const TWeakObjectPtr<AVLTroopShip>& S : Fleet->GetShips())
	{
		const AVLTroopShip* Ship = S.Get();
		if (!Ship || Ship->GetTeam() != UVLBattle::Mine())
		{
			continue;
		}
		TArray<AVLKing*> In;
		Ship->GetAboard(In);
		const int32 Heroes = In.FilterByPredicate([](const AVLKing* U) { return !U->IsTroop() || U->IsJonathan(); }).Num();
		if (In.Num() == 0 && Ship->NumComing() == 0 && Ship != Sel)
		{
			continue;
		}
		FVector2D At;
		if (PCtrl->ProjectWorldLocationToScreen(Ship->GetActorLocation() + FVector(0.f, 0.f, VLTroopShipDeck::RailZ + 420.f), At))
		{
			const FString Count = Heroes > 0 ? FString::Printf(TEXT("%d / %d  +  %d"), In.Num() - Heroes, AVLTroopShip::Capacity(), Heroes)
				: FString::Printf(TEXT("%d / %d"), In.Num(), AVLTroopShip::Capacity());
			Icon(EVLIcon::Shield, At.X - U(46.f), At.Y - U(2.f), U(18.f));
			Text(Count, At.X - U(24.f), At.Y - U(3.f), U(16.f), GoldBright, AlignLeft, Bold);
		}
	}
	// the selected ship's course: the troops' route lines (AVLHUD::DrawRouteLines), on the water. Blue: the corners
	// and the queued points of the course it sails; orange: a patrol's whole loop, a square on its first point
	if (Sel && Sel->GetTeam() == UVLBattle::Mine() && Command->NumSelected() == 0)
	{
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
			const FVector S = Project(B0 + Lift);
			if (S.Z > 0.f) { Fill(S.X - U(4.f), S.Y - U(4.f), U(8.f), U(8.f), Color); }
		};
		TArray<FVector> Course;
		bool bLoop = false;
		Sel->GetCourse(Course, bLoop);
		const FLinearColor Blue(0.55f, 0.8f, 1.f, 0.85f), Orange = VLStyle::PatrolViolet;     // (a patrol: violet, as the troops')
		if (bLoop)
		{
			for (int32 k = 0; k < Course.Num(); ++k)
			{
				if (Course.Num() == 2 && k == 1)
				{
					break;      // two points: one line, sailed both ways
				}
				Dashed(Course[k], Course[(k + 1) % Course.Num()], Orange);
			}
		}
		else
		{
			for (int32 k = 0; k + 1 < Course.Num(); ++k)
			{
				Dashed(Course[k], Course[k + 1], Blue);
			}
		}
	}
	// a berth in a ship's reach: the dock button over the place its gangplank would go (a click: it docks)
	for (const TWeakObjectPtr<AVLTroopShip>& S : Fleet->GetShips())
	{
		AVLTroopShip* Ship = S.Get();
		if (!Ship || Ship->GetTeam() != UVLBattle::Mine() || !Ship->CanDock())
		{
			continue;
		}
		const FVector At = Project(Ship->GetDockPoint() + FVector(0.f, 0.f, 260.f));
		if (At.Z <= 0.f)
		{
			continue;
		}
		const float Bob = U(3.f) * FMath::Sin(float(Now) * 4.f);
		const FBox2D R(FVector2D(At.X - U(27.f), At.Y - U(54.f) + Bob), FVector2D(At.X + U(27.f), At.Y + Bob));
		Block(R);
		const FBtn B = IconButton(R, VLId::Ship + 1, EVLIcon::ChevronDown, nullptr, true, true);
		Text(TEXT("DOCK"), At.X, R.Max.Y - U(15.f), U(11.f), GoldBright, AlignCentre, Bold);
		Fill(At.X - U(1.f), R.Max.Y, U(2.f), U(14.f), GoldBright);
		if (B.bHover)
		{
			SetTooltip(R, TEXT("Dock here"), { TEXT("The ship swings its side to the land and slides into this berth; its gangplank drops."),
				TEXT("Shown while a berth is within 30 m of the ship.") });
		}
		if (B.bClicked)
		{
			Click();
			if (Ship->Dock())
			{
				AVLGameMode::PlayOrderSound(this);
			}
		}
	}
	if (!Sel || Command->NumSelected() > 0)
	{
		return false;
	}
	const float DesignW = 760.f;
	const FFit Fit(*this, Room / FMath::Max(U(DesignW), 1.f));
	const FBox2D Box(FVector2D(X, Bottom - U(152.f)), FVector2D(X + FMath::Min(U(DesignW), FMath::Max(Room, 1.f)), Bottom));
	HudPanel(Box);
	const bool bMine = Sel->GetTeam() == UVLBattle::Mine();
	const float TX = Box.Min.X + U(18.f), TY = Box.Min.Y + U(12.f);
	TArray<AVLKing*> In;
	Sel->GetAboard(In);
	int32 Swords = 0, Bows = 0, Others = 0;
	FString Heroes;
	for (const AVLKing* Unit : In)
	{
		if (!Unit->IsTroop() || Unit->IsJonathan())
		{
			Heroes += (Heroes.IsEmpty() ? TEXT("") : TEXT(", ")) + Unit->GetDisplayName();
		}
		else if (Unit->IsRanged()) { ++Bows; }
		else if (Unit->GetKind() == TEXT("Swordsman")) { ++Swords; }
		else { ++Others; }
	}
	const int32 Troops = Swords + Bows + Others;
	Icon(EVLIcon::Shield, TX, TY, U(42.f), FLinearColor::White, !bMine);
	Text(bMine ? TEXT("Troop Ship") : TEXT("Enemy Troop Ship"), TX + U(52.f), TY - U(2.f), U(22.f), bMine ? GoldBright : FLinearColor(1.f, 0.55f, 0.45f, 1.f), AlignLeft, Bold);
	Text(Sel->DescribeState(), TX + U(52.f), TY + U(25.f), U(14.f), Dim);
	if (!bMine)
	{
		return true;
	}
	const float HY = TY + U(56.f);
	Meter(TX, HY, U(260.f), U(10.f), float(Troops) / FMath::Max(AVLTroopShip::Capacity(), 1), GoldBright);
	Text(FString::Printf(TEXT("%d / %d aboard"), Troops, AVLTroopShip::Capacity()), TX + U(270.f), HY - U(5.f), U(15.f), Parchment, AlignLeft, Bold);
	FString Line = FString::Printf(TEXT("%d swordsmen  -  %d archers"), Swords, Bows);
	if (Others > 0) { Line += FString::Printf(TEXT("  -  %d others"), Others); }
	if (!Heroes.IsEmpty()) { Line += TEXT("  -  ") + Heroes; }
	if (Sel->NumComing() > 0) { Line += FString::Printf(TEXT("  -  %d coming"), Sel->NumComing()); }
	Text(Line, TX, HY + U(22.f), U(14.f), Parchment);
	Text(Sel->IsLanded() ? TEXT("Right click the water to sail (Shift: more points).  P: patrol.  Troops: right click the ship.") : TEXT("Right click the water to sail (Shift: more points); a shore or a quay to dock.  P: patrol."),
		TX, HY + U(46.f), U(13.f), Dim);

	// Unload: everyone down the gangplank
	const float RW = U(190.f);
	const FBox2D R(FVector2D(Box.Max.X - U(16.f) - RW, Box.Min.Y + U(16.f)), FVector2D(Box.Max.X - U(16.f), Box.Max.Y - U(16.f)));
	const bool bEnabled = Sel->IsLanded() && In.Num() > 0;
	FBtn B = Button(R, VLId::Ship, bEnabled);
	if (!bEnabled) { B.Hot *= 0.3f; }
	ButtonFrame(R, B, bEnabled);
	const float Lift = B.bHeld ? U(1.f) : 0.f;
	Icon(EVLIcon::ChevronDown, R.Min.X + U(14.f), R.Min.Y + U(16.f) + Lift, U(34.f), bEnabled ? FLinearColor::White : FLinearColor(0.45f, 0.45f, 0.5f, 0.85f));
	Text(TEXT("Unload"), R.Min.X + U(62.f), R.Min.Y + U(30.f) + Lift, U(14.f), bEnabled ? Parchment : Dim, AlignLeft, Bold);
	Text(FString::Printf(TEXT("%d"), In.Num()), R.Min.X + U(62.f), R.Min.Y + U(52.f) + Lift, U(16.f), bEnabled ? GoldBright : Dim, AlignLeft, Bold);
	Text(bEnabled ? TEXT("Click: all ashore") : (In.Num() > 0 ? TEXT("Land it first") : TEXT("Nobody aboard")), R.Min.X + U(10.f), R.Max.Y - U(26.f) + Lift, U(13.f), Dim);
	if (B.bHover)
	{
		SetTooltip(R, FString::Printf(TEXT("Troop ship: %d of %d soldiers aboard"), Troops, AVLTroopShip::Capacity()), {
			TEXT("It carries 24 soldiers; King David and Jonathan stand on its stern castle and take no soldier's place."),
			TEXT("Board: select troops and right-click the ship while its gangplank is out."),
			TEXT("Sail: with the ship selected, right-click the water; a shore or a quay to land there."),
			TEXT("Click: everyone goes down the gangplank and forms up on the shore.") });
	}
	if (B.bClicked && bEnabled)
	{
		Click();
		if (Sel->Unload() > 0)
		{
			AVLGameMode::PlayOrderSound(this);
		}
	}
	// Dock: beside it, while a berth is in reach
	if (Sel->CanDock())
	{
		const float DW = U(96.f);
		const FBox2D D(FVector2D(R.Min.X - U(10.f) - DW, R.Min.Y), FVector2D(R.Min.X - U(10.f), R.Max.Y));
		const FBtn DB = Button(D, VLId::Ship + 2, true);
		ButtonFrame(D, DB, true, true);
		const float DL = DB.bHeld ? U(1.f) : 0.f;
		Icon(EVLIcon::ChevronDown, D.Min.X + (DW - U(34.f)) * 0.5f, D.Min.Y + U(18.f) + DL, U(34.f));
		Text(TEXT("Dock"), (D.Min.X + D.Max.X) * 0.5f, D.Min.Y + U(64.f) + DL, U(14.f), GoldBright, AlignCentre, Bold);
		Text(TEXT("a berth in reach"), (D.Min.X + D.Max.X) * 0.5f, D.Max.Y - U(26.f) + DL, U(11.f), Dim, AlignCentre);
		if (DB.bClicked)
		{
			Click();
			if (Sel->Dock())
			{
				AVLGameMode::PlayOrderSound(this);
			}
		}
	}
	return true;
}
