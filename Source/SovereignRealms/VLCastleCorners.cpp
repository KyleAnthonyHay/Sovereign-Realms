// The castle's corners (the owner's call, 2026-11-23): "add archers to the corners of the castle, and let the corners
// have hitboxes ... The corners should have their own hitbox and health, but once that's destroyed, there's no more
// archer to shoot, and it will max out at 4 for the 4 corners. The only way that's fixed is if a builder repairs, and
// that costs money."
//
//   manning    the castle's archers (its level's Archers: 1, 2, 2, 3, 3, 4, 4) stand one to a corner turret, the front
//              two first (0 front left, 1 front right), then the back two: VLRules::CastleCorners(level)
//   hit boxes  each turret of SM_Castle (Tools/blender/assets/castle.py: 18 x 18 voxels of 12.5 cm, 50 high; their
//              footprints' middles at x -437.5 / +487.5 cm, y +250 (the front) / -450 cm in the actor's space), grown
//              by VLRules::BuildingHitPad for an arrow (where it lands) and by MeleeBuildingPad + 80 for a blade (where
//              the one swinging it stands). What lands in a manned, standing corner hurts that corner, not the castle
//   health     VLRules::CornerHealthShare of the castle's at its level (1008 .. 2520); whole again with every level
//   falling    at 0 the corner's archer is gone (its figure taken away, no more shots from it) until it is mended
//   repairs    paid up front in gold (VLRules::CornerRepairGoldPerHp a point lacking, at least CornerRepairMinGold;
//              every damaged corner at once): the castle panel's Repair button, or Builders ordered onto the castle
//              (UVLConstruction::OrderWork). Builders at the castle then mend the paid corners one after the other at
//              VLBuild::RepairPerSecond each a second; a mended corner's archer is back. The enemy's commander pays
//              for its own once nothing has hit the castle for 10 s and it has the gold and 100 over
//   aiming     an arrow at a castle (UVLBattle::AimPoint) goes for the standing corner nearest the archer first
// The archers' figures are the archer troop's parts (DA_Archer) at rest, on the turret's lookout floor, turned to what
// they shoot at: no units (no AI, housing, selection or saving of their own); the castle shoots for them (TickDefence).
// Console: vl.Corners (every castle's corners), vl.Corners hit <0-3> <amount> [enemy], vl.Corners repair [enemy].

#include "VLBattle.h"
#include "SovereignRealms.h"
#include "VLArrow.h"
#include "VLCharacterData.h"
#include "VLConstruction.h"
#include "VLEnemyAI.h"
#include "VLKing.h"
#include "VLTroop.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "HAL/IConsoleManager.h"

namespace
{
	// the turrets' footprints' middles, in the actor's space (cm): 0 front left, 1 front right, 2 back left, 3 back right
	const FVector2D CornerXY[VLRules::MaxCorners] = { { -437.5f, 250.f }, { 487.5f, 250.f }, { -437.5f, -450.f }, { 487.5f, -450.f } };
	constexpr float TurretHalf = 112.5f;        // half the turret's footprint (cm)
	constexpr float TurretTop = 625.f;          // the top of its merlons
	constexpr float LookoutFloor = 550.f;       // where its archer stands
	const TCHAR* CornerName[VLRules::MaxCorners] = { TEXT("front left"), TEXT("front right"), TEXT("back left"), TEXT("back right") };
}

int32 VLRules::CastleCorners(int32 InLevel)
{
	return FMath::Clamp(Level(EVLBuilding::Castle, InLevel).Archers, 0, MaxCorners);
}

FVector UVLBattle::CornerPoint(const AActor* Castle, int32 Corner, float Z) const
{
	if (!Castle)
	{
		return FVector::ZeroVector;
	}
	const FVector2D& C = CornerXY[FMath::Clamp(Corner, 0, VLRules::MaxCorners - 1)];
	return Castle->GetActorTransform().TransformPosition(FVector(C.X, C.Y, Z));
}

bool UVLBattle::IsCornerUp(const FVLBuildingState& B, int32 Corner) const
{
	return B.Kind == EVLBuilding::Castle && B.IsAlive() && !B.IsSite() && Corner >= 0 && Corner < VLRules::CastleCorners(B.Level) && !B.bCornerDown[Corner]
		&& B.CornerHealth[Corner] > 0.f;
}

float UVLBattle::CornerMaxHealth(const FVLBuildingState& B) const
{
	return VLRules::CornerHealthShare * VLRules::Level(EVLBuilding::Castle, B.Level).Health;
}

int32 UVLBattle::CornerAt(const FVLBuildingState& B, const FVector& P, float Pad) const
{
	const AActor* A = B.Actor.Get();
	if (!A || B.Kind != EVLBuilding::Castle)
	{
		return INDEX_NONE;
	}
	const FVector L = A->GetActorTransform().InverseTransformPosition(P);
	if (L.Z > TurretTop + Pad)
	{
		return INDEX_NONE;
	}
	for (int32 i = 0; i < VLRules::MaxCorners; ++i)
	{
		if (IsCornerUp(B, i) && FMath::Abs(L.X - CornerXY[i].X) <= TurretHalf + Pad && FMath::Abs(L.Y - CornerXY[i].Y) <= TurretHalf + Pad)
		{
			return i;
		}
	}
	return INDEX_NONE;
}

int32 UVLBattle::CornerNear(const FVLBuildingState& B, const FVector& P, float Reach) const
{
	const AActor* A = B.Actor.Get();
	if (!A || B.Kind != EVLBuilding::Castle)
	{
		return INDEX_NONE;
	}
	const FTransform Xf = A->GetActorTransform();
	const FVector L = Xf.InverseTransformPosition(P);
	const float Scale = FMath::Max(Xf.GetScale3D().X, 0.01f);
	int32 Best = INDEX_NONE;
	float BestD = Reach / Scale;
	for (int32 i = 0; i < VLRules::MaxCorners; ++i)
	{
		if (!IsCornerUp(B, i))
		{
			continue;
		}
		const float DX = FMath::Max(0.f, FMath::Abs(L.X - CornerXY[i].X) - TurretHalf), DY = FMath::Max(0.f, FMath::Abs(L.Y - CornerXY[i].Y) - TurretHalf);
		const float D = FMath::Sqrt(DX * DX + DY * DY);
		if (D <= BestD)
		{
			BestD = D;
			Best = i;
		}
	}
	return Best;
}

int32 UVLBattle::CornerAlong(const FVLBuildingState& B, const FVector& At, const FVector& Dir, float Ahead) const
{
	// (the arrow strikes the castle's box where it enters it; one flying on at a turret behind its front walls or
	// porch is the turret's: it was aimed at it, UVLBattle::AimPoint)
	const FVector D = Dir.GetSafeNormal();
	for (float T = 0.f; T <= Ahead; T += 25.f)
	{
		const int32 C = CornerAt(B, At + D * T, VLRules::BuildingHitPad);
		if (C != INDEX_NONE || D.IsNearlyZero())
		{
			return C;
		}
	}
	return INDEX_NONE;
}

int32 UVLBattle::NearestUpCorner(const FVLBuildingState& B, const FVector& From) const
{
	int32 Best = INDEX_NONE;
	float BestD = TNumericLimits<float>::Max();
	for (int32 i = 0; i < VLRules::MaxCorners; ++i)
	{
		if (IsCornerUp(B, i))
		{
			const float D = FVector::DistSquared2D(CornerPoint(B.Actor.Get(), i, 0.f), From);
			if (D < BestD)
			{
				BestD = D;
				Best = i;
			}
		}
	}
	return Best;
}

int32 UVLBattle::CornerRepairCost(const FVLBuildingState& B) const
{
	if (B.Kind != EVLBuilding::Castle || !B.IsAlive() || B.IsSite())
	{
		return 0;
	}
	const float Max = CornerMaxHealth(B);
	float Lacking = 0.f;
	for (int32 i = 0; i < VLRules::CastleCorners(B.Level); ++i)
	{
		if (!B.bCornerRepair[i] && B.CornerHealth[i] < Max - 0.5f)
		{
			Lacking += Max - B.CornerHealth[i];
		}
	}
	return Lacking <= 0.f ? 0 : FMath::Max(VLRules::CornerRepairMinGold, FMath::CeilToInt(Lacking * VLRules::CornerRepairGoldPerHp));
}

bool UVLBattle::PayCornerRepair(AActor* Castle, bool bQuiet)
{
	FVLBuildingState* B = FindBuilding(Castle);
	const int32 Cost = B ? CornerRepairCost(*B) : 0;
	if (!B || Cost <= 0 || (B->Team != Player && B->Team != Enemy))
	{
		return false;
	}
	FVLCost Price;
	Price.Gold = Cost;
	if (!TrySpend(B->Team, Price, bQuiet))
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("CORNERS %s of team %d: a repair would cost %d gold: refused"), *B->Name, B->Team, Cost);
		return false;
	}
	const float Max = CornerMaxHealth(*B);
	int32 N = 0;
	for (int32 i = 0; i < VLRules::CastleCorners(B->Level); ++i)
	{
		if (!B->bCornerRepair[i] && B->CornerHealth[i] < Max - 0.5f)
		{
			B->bCornerRepair[i] = true;
			++N;
		}
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("CORNERS %s of team %d: %d corner(s) paid to be mended, %d gold; Builders at the castle mend them"), *B->Name, B->Team, N, Cost);
	if (B->Team == Player && !bQuiet)
	{
		PushAlert(FString::Printf(TEXT("Corner repair paid: %d gold. Builders at the castle mend it"), Cost), EVLAlert::Good);
	}
	return true;
}

float UVLBattle::DamageAt(AActor* Target, float Amount, AActor* By, int32 ByTeam, const FVector& At, const FVector& Dir)
{
	HitAt = At;
	HitDir = Dir.GetSafeNormal();
	bHitAt = true;
	const float Done = Damage(Target, Amount, By, ByTeam);
	bHitAt = false;
	return Done;
}

void UVLBattle::ShowCornerFigure(FVLBuildingState& B, int32 Corner, bool bShow)
{
	AActor* A = B.Actor.Get();
	USceneComponent* Root = B.CornerFigure[Corner].Get();
	if (!bShow)
	{
		if (Root && Root->IsVisible())
		{
			Root->SetVisibility(false, true);
		}
		return;
	}
	if (!A)
	{
		return;
	}
	if (!Root)
	{
		// the archer troop's parts at rest, as AVLKing::BuildFigure hangs them (no joints to swing: a pose that stands)
		const UVLCharacterData* Data = AVLTroop::DataFor(TEXT("Archer")).LoadSynchronous();
		if (!Data)
		{
			return;
		}
		Root = NewObject<USceneComponent>(A, *FString::Printf(TEXT("CornerArcher%d"), Corner));
		Root->SetupAttachment(A->GetRootComponent());
		Root->SetAbsolute(false, false, true);          // (the castle may be scaled: the archer is not)
		Root->RegisterComponent();
		for (const FVLPart& P : Data->Parts)
		{
			if (!P.Mesh)
			{
				continue;
			}
			UStaticMeshComponent* M = NewObject<UStaticMeshComponent>(A, *FString::Printf(TEXT("CornerArcher%d_%s"), Corner, *P.Name.ToString()));
			M->SetStaticMesh(P.Mesh);
			M->SetupAttachment(Root);
			M->SetRelativeLocation(P.Pivot);
			M->SetRelativeRotation(FRotator(0.f, Data->MeshYaw, 0.f));
			M->SetCollisionEnabled(ECollisionEnabled::NoCollision);
			M->SetCastShadow(true);
			M->bAffectDistanceFieldLighting = false;
			M->bAffectDynamicIndirectLighting = false;
			AVLKing::ApplyPartLook(M, B.Team);
			M->RegisterComponent();
		}
		B.CornerFigure[Corner] = Root;
	}
	Root->SetWorldLocationAndRotation(CornerPoint(A, Corner, LookoutFloor), FRotator(0.f, B.CornerYaw[Corner], 0.f));
	Root->SetWorldScale3D(FVector::OneVector);
	if (!Root->IsVisible())
	{
		Root->SetVisibility(true, true);
	}
}

void UVLBattle::TickCastleCorners(float Dt)
{
	const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
	for (FVLBuildingState& B : Buildings)
	{
		if (B.Kind != EVLBuilding::Castle)
		{
			continue;
		}
		AActor* A = B.Actor.Get();
		if (!B.IsAlive() || B.IsSite())
		{
			for (int32 i = 0; i < VLRules::MaxCorners; ++i)
			{
				ShowCornerFigure(B, i, false);
			}
			continue;
		}
		const int32 Manned = VLRules::CastleCorners(B.Level);
		const float Max = CornerMaxHealth(B);
		// a new level (or the first look at it): every manned corner whole, its archer up, facing out from the castle
		if (B.CornerLevel != B.Level)
		{
			for (int32 i = 0; i < VLRules::MaxCorners; ++i)
			{
				B.CornerHealth[i] = i < Manned ? Max : 0.f;
				B.bCornerDown[i] = false;
				B.bCornerRepair[i] = false;
				const FVector Out = CornerPoint(A, i, 0.f) - A->GetActorLocation();
				B.CornerYaw[i] = Out.Rotation().Yaw;
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("CORNERS %s of team %d at level %d: %d manned, %.0f health each"), *B.Name, B.Team, B.Level, Manned, Max);
			B.CornerLevel = B.Level;
		}
		// Builders at the castle mend the paid corners, one after the other
		if (B.BuildersAt > 0)
		{
			for (int32 i = 0; i < Manned; ++i)
			{
				if (!B.bCornerRepair[i])
				{
					continue;
				}
				B.CornerHealth[i] = FMath::Min(Max, B.CornerHealth[i] + B.BuildersAt * VLBuild::RepairPerSecond * Dt);
				if (B.CornerHealth[i] >= Max - 0.01f)
				{
					B.CornerHealth[i] = Max;
					B.bCornerRepair[i] = false;
					const bool bWasDown = B.bCornerDown[i];
					B.bCornerDown[i] = false;
					UE_LOG(LogSovereignRealms, Log, TEXT("CORNERS %s of team %d: the %s corner mended%s"), *B.Name, B.Team, CornerName[i], bWasDown ? TEXT(": its archer is back") : TEXT(""));
					if (B.Team == Player)
					{
						const FVector At = CornerPoint(A, i);
						PushAlert(bWasDown ? FString::Printf(TEXT("The castle's %s corner is mended: its archer is back"), CornerName[i])
							: FString::Printf(TEXT("The castle's %s corner is mended"), CornerName[i]), EVLAlert::Good, &At);
					}
				}
				break;
			}
		}
		// the commander's repairs: once the castle has been left alone a while, and the gold is there with some over
		if (const FVLCommander* C = GetCommander(B.Team); C && C->bActive && Now - B.LastHit > 10.0)
		{
			const int32 Cost = CornerRepairCost(B);
			if (Cost > 0 && GetStock(B.Team, EVLRes::Gold) >= Cost + 100)
			{
				PayCornerRepair(A, true);
			}
		}
		for (int32 i = 0; i < VLRules::MaxCorners; ++i)
		{
			ShowCornerFigure(B, i, IsCornerUp(B, i));
		}
	}
}

void UVLBattle::ShootFromCorners(FVLBuildingState& B, const TArray<TPair<float, AVLKing*>, TInlineAllocator<32>>& InReach)
{
	UVLArrows* Arrows = UVLArrows::Get(this);
	AActor* A = B.Actor.Get();
	if (!Arrows || !A)
	{
		return;
	}
	const VLRules::FLevel& L = VLRules::Level(EVLBuilding::Castle, B.Level);
	for (int32 k = 0; k < VLRules::MaxCorners; ++k)
	{
		if (!IsCornerUp(B, k))
		{
			continue;               // (a corner knocked out has no archer)
		}
		// the foe nearest this corner, within the castle's reach of it (its walls' reach and the turret's half)
		const FVector Me = CornerPoint(A, k, 0.f);
		AVLKing* Mark = nullptr;
		float BestD = FMath::Square(L.Range + 700.f);
		for (const TPair<float, AVLKing*>& P : InReach)
		{
			const float D = FVector::DistSquared2D(P.Value->GetFeet(), Me);
			if (D < BestD)
			{
				BestD = D;
				Mark = P.Value;
			}
		}
		if (!Mark)
		{
			continue;
		}
		// from the archer's bow on the turret, aimed where the mark will be when the arrow gets there
		FVector Muzzle = CornerPoint(A, k, LookoutFloor + 140.f);
		const float Speed = 5200.f;
		FVector Aim = Mark->GetActorLocation() + FVector(0.f, 0.f, 10.f);
		Aim += Mark->GetVelocity() * (FVector::Dist(Muzzle, Aim) / Speed);
		const float Gravity = UVLArrows::ArcGravity(float(FVector::Dist2D(Muzzle, Aim)), Speed, 980.f, 50.f, 2000.f, 1.f);
		FVector Dir;
		UVLArrows::SolveArc(Muzzle, Aim, Speed, Gravity, Dir);
		Muzzle += Dir * 60.f;           // (clear of the merlons)
		Arrows->FireFrom(A, B.Team, Muzzle, Dir * Speed, Gravity, L.Damage);
		B.CornerYaw[k] = (Aim - Muzzle).Rotation().Yaw;      // (its figure turns to it: TickCastleCorners)
	}
}

// ------------------------------------------------------------------------------------------------ console

namespace
{
	FVLBuildingState* CastleOf(UVLBattle* Battle, int32 Team)
	{
		AActor* C = Battle ? Battle->GetCastle(Team) : nullptr;
		return C ? Battle->FindBuilding(C) : nullptr;
	}

	FAutoConsoleCommandWithWorldAndArgs CmdCorners(TEXT("vl.Corners"),
		TEXT("vl.Corners: every castle's corners | vl.Corners hit <0-3> <amount> [enemy]: as an arrow landing on that corner (from the other side) | vl.Corners repair [enemy]: pay for the repair"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLBattle* Battle = UVLBattle::Get(World);
			if (!Battle)
			{
				return;
			}
			const bool bEnemy = Args.ContainsByPredicate([](const FString& S) { return S.Equals(TEXT("enemy"), ESearchCase::IgnoreCase); });
			const int32 Team = bEnemy ? UVLBattle::Enemy : UVLBattle::Player;
			FVLBuildingState* B = CastleOf(Battle, Team);
			if (Args.Num() >= 3 && Args[0].Equals(TEXT("hit"), ESearchCase::IgnoreCase) && B)
			{
				const int32 Corner = FMath::Clamp(FCString::Atoi(*Args[1]), 0, 3);
				const float Amount = FCString::Atof(*Args[2]);
				const FVector At = Battle->CornerPoint(B->Actor.Get(), Corner, 400.f);
				// (an archer's arrow is halved against stone: twice the amount, so the corner loses what was asked)
				const float Done = Battle->DamageAt(B->Actor.Get(), Amount / VLRules::Troop(EVLUnitKind::Archer).BuildingScale, nullptr, 1 - Team, At);
				UE_LOG(LogSovereignRealms, Log, TEXT("vl.Corners hit %d: %.0f dealt; corner %.0f, castle %.0f / %.0f"), Corner, Done, B->CornerHealth[Corner], B->Health, B->MaxHealth);
				return;
			}
			if (Args.Num() >= 1 && Args[0].Equals(TEXT("repair"), ESearchCase::IgnoreCase) && B)
			{
				const int32 Cost = Battle->CornerRepairCost(*B);
				const bool bPaid = Battle->PayCornerRepair(B->Actor.Get());
				UE_LOG(LogSovereignRealms, Log, TEXT("vl.Corners repair: %d gold, %s"), Cost, bPaid ? TEXT("paid") : TEXT("not paid"));
				return;
			}
			for (const FVLBuildingState& S : Battle->GetBuildings())
			{
				if (S.Kind != EVLBuilding::Castle || !S.Actor.IsValid())
				{
					continue;
				}
				FString Line;
				for (int32 i = 0; i < VLRules::MaxCorners; ++i)
				{
					const FVector P = Battle->CornerPoint(S.Actor.Get(), i);
					Line += FString::Printf(TEXT(" | %d %s: %s %.0f%s%s at %.0f %.0f %.0f"), i, CornerName[i], i < VLRules::CastleCorners(S.Level) ? TEXT("manned") : TEXT("empty"),
						S.CornerHealth[i], S.bCornerDown[i] ? TEXT(" DOWN") : TEXT(""), S.bCornerRepair[i] ? TEXT(" (repair paid)") : TEXT(""), P.X, P.Y, P.Z);
				}
				UE_LOG(LogSovereignRealms, Log, TEXT("CORNERS %s of team %d, level %d (max %.0f each, repair %d gold, %d Builder(s) at it):%s"), *S.Name, S.Team, S.Level,
					Battle->CornerMaxHealth(S), Battle->CornerRepairCost(S), S.BuildersAt, *Line);
			}
		}));
}
