// Copyright Sovereign Realms.

#include "FX/SRWildlife.h"
#include "SovereignRealms.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SREconomySubsystem.h"
#include "Battle/SRFogSubsystem.h"
#include "Battle/SRGridSubsystem.h"
#include "Buildings/SRBuilding.h"
#include "Common/SRFeelSettings.h"
#include "Units/SRSprite.h"
#include "Units/SRUnit.h"
#include "Components/StaticMeshComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "HAL/IConsoleManager.h"


namespace
{
	// Sheet blocks (the troops' layout, SRSprite.cpp; what they mean for an animal: Tools/blender/char_deer.py).
	constexpr int32 GrazeCol = 0, GrazeRow = 0, GrazeFrames = 6;
	constexpr int32 StandCol = 8, StandRow = 0;
	constexpr int32 WalkCol = 16, WalkRow = 0;
	constexpr int32 BoltCol = 0, BoltRow = 8;
	constexpr int32 StartCol = 8, StartRow = 8, StartFrames = 3;
	constexpr int32 LookCol = 16, LookRow = 8;
	constexpr float WalkCycleCm = 96.f, BoltCycleCm = 200.f;

	UStaticMeshComponent* MakeCard(AActor* Owner, UStaticMesh* Mesh, UMaterialInterface* Material, bool bShadowOnly)
	{
		UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(Owner);
		C->SetMobility(EComponentMobility::Movable);
		C->SetStaticMesh(Mesh);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetGenerateOverlapEvents(false);
		C->SetCanEverAffectNavigation(false);
		C->bReceivesDecals = false;
		C->bAffectDynamicIndirectLighting = false;
		C->bAffectDistanceFieldLighting = false;
		C->bVisibleInRayTracing = false;
		C->SetUsingAbsoluteLocation(true);
		C->SetUsingAbsoluteRotation(true);
		C->SetUsingAbsoluteScale(true);
		if (bShadowOnly)
		{
			C->SetCastShadow(true);
			C->bCastHiddenShadow = true;
			C->SetHiddenInGame(true);
			C->ShadowCacheInvalidationBehavior = EShadowCacheInvalidationBehavior::Always;
		}
		else
		{
			C->SetCastShadow(false);
			C->SetBoundsScale(2.f);
		}
		C->SetupAttachment(Owner->GetRootComponent());
		C->RegisterComponent();
		C->SetMaterial(0, Material);
		return C;
	}

	FAutoConsoleCommandWithWorldAndArgs CmdWildlife(TEXT("sr.Wildlife"), TEXT("Log where each herd is and whether it is alarmed."),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			for (TActorIterator<ASRWildlife> It(World); It; ++It)
			{
				FString Line;
				for (int32 i = 0; i < It->NumHerds(); ++i)
				{
					const FVector2D P = It->HerdCentre(i);
					Line += FString::Printf(TEXT(" [%d](%.0f,%.0f)%s"), i, P.X, P.Y, It->IsHerdAlarmed(i) ? TEXT("!") : TEXT(""));
				}
				UE_LOG(LogSovereign, Log, TEXT("WILDLIFE %d deer in %d herds, %d bolting:%s"), It->NumAnimals(), It->NumHerds(), It->NumFleeing(), *Line);
			}
		}));
}

ASRWildlife::ASRWildlife()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostUpdateWork;   // after the battle subsystem has set this frame's sprite view
	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
}

int32 ASRWildlife::NumFleeing() const
{
	int32 N = 0;
	for (const FAnimal& A : Animals) { N += (A.State == EState::Flee || A.State == EState::Start) ? 1 : 0; }
	return N;
}

bool ASRWildlife::GoodGround(const FVector2D& P, bool bRoomy) const
{
	const USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	const USRFeelSettings& F = USRFeelSettings::Get();
	FIntPoint C;
	if (!Grid || !Grid->ToCell(P, C) || !Grid->IsWalkable(C) || Grid->IsWater(C)) { return false; }
	if (FMath::Abs(P.X) > F.MapHalfExtent.X - 400.f || FMath::Abs(P.Y) > F.MapHalfExtent.Y - 400.f) { return false; }
	if (!bRoomy) { return true; }
	// a herd's home: level, open ground with room all round (no knoll top, no ledge, no bank)
	const float Z = Grid->CellHeight(C);
	// (the terraced map, which has no water sheets: not on the wet shore, nor up on the heights. On the heightfield
	// maps the meadows lie at every height, and the water is known by its sheets.)
	const bool bSheets = Grid->UsesWaterSheets();
	if (!bSheets && (Z < -5.f || Z > 420.f)) { return false; }
	for (int32 k = 0; k < 16; ++k)
	{
		const float A = k * PI / 8.f;
		const float R = (k % 2 == 0) ? 350.f : 700.f;
		FIntPoint N;
		// level: within a step on flat terraces; on rolling ground, a gentle slope (one in eight) all round
		const float Level = bSheets ? FMath::Max(F.StepHeight, R * 0.125f) : F.StepHeight;
		if (!Grid->ToCell(P + FVector2D(FMath::Cos(A), FMath::Sin(A)) * R, N) || !Grid->IsWalkable(N) || Grid->IsWater(N)
			|| FMath::Abs(Grid->CellHeight(N) - Z) > Level) { return false; }
	}
	if (const USREconomySubsystem* Eco = USREconomySubsystem::Get(this))
	{
		for (const ASRBuilding* B : Eco->GetBuildings())
		{
			if (!B) { continue; }
			const float Keep = B->BuildingType == ESRBuildingType::Castle ? F.WildlifeKeepFromCastle : F.WildlifeKeepFromBuildings;
			if (FVector2D::DistSquared(B->GetFootprintCentre(), P) < FMath::Square(Keep)) { return false; }
		}
	}
	return true;
}

bool ASRWildlife::Init()
{
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	const USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (!Battle || !Battle->UnitCardMesh || !Grid || !Grid->IsBuilt()) { return false; }
	SetActorTransform(FTransform::Identity);
	Rng.Initialize(1907);

	// stag, hind: sprite + shadow
	static const TCHAR* Paths[4] = {
		TEXT("/Game/SR/Materials/MI_UnitSprite_Deer.MI_UnitSprite_Deer"), TEXT("/Game/SR/Materials/MI_UnitSprite_Doe.MI_UnitSprite_Doe"),
		TEXT("/Game/SR/Materials/MI_UnitSpriteShadow_Deer.MI_UnitSpriteShadow_Deer"), TEXT("/Game/SR/Materials/MI_UnitSpriteShadow_Doe.MI_UnitSpriteShadow_Doe") };
	for (int32 i = 0; i < 4; ++i)
	{
		UMaterialInterface* Base = LoadObject<UMaterialInterface>(nullptr, Paths[i], nullptr, LOAD_NoWarn | LOAD_Quiet);
		if (!Base)
		{
			UE_LOG(LogSovereign, Warning, TEXT("WILDLIFE no %s (import the deer sheets and build the sprite materials): no wildlife"), Paths[i]);
			return true;   // ready, with nothing in it
		}
		UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(Base, this);
		if (i < 2)
		{
			MID->SetScalarParameterValue(TEXT("Relight"), F.SpriteRelight);
			MID->SetScalarParameterValue(TEXT("BakedLight"), F.SpriteBakedLight);
			MID->SetScalarParameterValue(TEXT("EdgeSoftness"), F.SpriteEdgeSoftness);
			MID->SetScalarParameterValue(TEXT("NormalStrength"), F.SpriteNormalStrength);
		}
		Materials.Add(MID);
	}

	const float HalfX = F.MapHalfExtent.X - 1500.f, HalfY = F.MapHalfExtent.Y - 1500.f;
	for (int32 h = 0; h < F.WildlifeHerds; ++h)
	{
		FHerd H;
		bool bFound = false;
		for (int32 Try = 0; Try < 400 && !bFound; ++Try)
		{
			// herds are dealt out over a coarse lattice so they spread across the whole map, not bunch in one meadow
			const FVector2D P(Rng.FRandRange(-HalfX, HalfX), Rng.FRandRange(-HalfY, HalfY));
			if (!GoodGround(P, true)) { continue; }
			bool bFar = true;
			for (const FHerd& O : Herds) { bFar &= FVector2D::DistSquared(O.Centre, P) > FMath::Square(F.WildlifeHerdSpacing); }
			if (!bFar) { continue; }
			H.Centre = P;
			bFound = true;
		}
		if (!bFound) { continue; }
		H.Spread = Rng.FRandRange(450.f, 750.f);
		H.DriftTimer = Rng.FRandRange(20.f, 70.f);
		H.ScanTimer = Rng.FRandRange(0.f, 0.3f);
		const int32 HerdIndex = Herds.Add(H);
		const int32 Count = Rng.RandRange(FMath::Max(1, F.WildlifeHerdSize.X), FMath::Max(F.WildlifeHerdSize.X, F.WildlifeHerdSize.Y));
		for (int32 i = 0; i < Count; ++i)
		{
			FAnimal A;
			A.Herd = HerdIndex;
			A.Kind = (i == 0 || (i == 4 && Rng.FRand() < 0.4f)) ? 0 : 1;             // a stag leads; a big herd may have a second
			A.Scale = A.Kind == 0 ? Rng.FRandRange(1.0f, 1.08f) : ((i >= 3 && Rng.FRand() < 0.5f) ? Rng.FRandRange(0.62f, 0.72f) : Rng.FRandRange(0.9f, 1.0f));
			A.Pos = H.Centre;
			for (int32 Try = 0; Try < 30; ++Try)
			{
				const float Ang = Rng.FRandRange(0.f, 2.f * PI);
				const FVector2D P = H.Centre + FVector2D(FMath::Cos(Ang), FMath::Sin(Ang)) * Rng.FRandRange(120.f, H.Spread);
				if (GoodGround(P, false) && Grid->CanWalkStraight(H.Centre, P)) { A.Pos = P; break; }
			}
			A.Yaw = Rng.FRandRange(-180.f, 180.f);
			A.Nerve = Rng.FRandRange(0.75f, 1.15f);
			A.Veer = Rng.FRandRange(-22.f, 22.f);
			A.Clock = Rng.FRandRange(0.f, 10.f);
			Grid->HeightAt(A.Pos, A.Z);
			A.Card = MakeCard(this, Battle->UnitCardMesh, Materials[A.Kind], false);
			A.ShadowCard = MakeCard(this, Battle->UnitCardMesh, Materials[2 + A.Kind], true);
			A.Card->SetCustomPrimitiveDataVector4(SRSprite::DataTeamColor, FVector4(1.f, 1.f, 1.f, 1.f));
			A.Card->SetWorldScale3D(FVector(A.Scale));
			Cards.Add(A.Card);
			Cards.Add(A.ShadowCard);
			Begin(A, Rng.FRand() < 0.6f ? EState::Graze : EState::Stand);
			A.StateTime = Rng.FRandRange(0.f, A.StateDuration);
			Animals.Add(A);
		}
	}
	UE_LOG(LogSovereign, Log, TEXT("WILDLIFE %d deer in %d herds"), Animals.Num(), Herds.Num());
	return true;
}

void ASRWildlife::Begin(FAnimal& A, EState NewState)
{
	A.State = NewState;
	A.StateTime = 0.f;
	A.Distance = 0.f;
	switch (NewState)
	{
	case EState::Graze: A.StateDuration = Rng.FRandRange(5.f, 14.f); break;
	case EState::Stand: A.StateDuration = Rng.FRandRange(1.5f, 5.f); break;
	case EState::Look: A.StateDuration = 8.f / 3.f; break;                 // one sweep of the head
	case EState::Walk: A.StateDuration = 20.f; break;
	case EState::Start: A.StateDuration = Rng.FRandRange(0.28f, 0.5f); break;
	case EState::Flee: A.StateDuration = Rng.FRandRange(2.5f, 3.5f); break;  // at least this long
	}
}

bool ASRWildlife::Step(FAnimal& A, const FVector2D& Dir, float Dist) const
{
	const USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	const float StepHeight = USRFeelSettings::Get().StepHeight;
	FIntPoint From, To, Ahead;
	const FVector2D New = A.Pos + Dir * Dist;
	if (!Grid || !Grid->ToCell(A.Pos, From) || !GoodGround(New, false) || !Grid->ToCell(New, To)) { return false; }
	if (FMath::Abs(Grid->CellHeight(To) - Grid->CellHeight(From)) > StepHeight) { return false; }
	// and look a stride ahead, so it turns before the bank or the cliff instead of at it
	const FVector2D Look = A.Pos + Dir * FMath::Max(Dist, 160.f);
	if (!GoodGround(Look, false) || !Grid->ToCell(Look, Ahead) || FMath::Abs(Grid->CellHeight(Ahead) - Grid->CellHeight(To)) > StepHeight) { return false; }
	A.Pos = New;
	return true;
}

void ASRWildlife::Think(FAnimal& A, FHerd& H, float Dt)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	A.StateTime += Dt;
	A.Clock += Dt;
	const FVector2D FromThreat = A.Pos - H.Threat;
	const float ThreatDist = FromThreat.Size();

	if (H.bAlarmed && A.State != EState::Flee && A.State != EState::Start && ThreatDist < F.WildlifeFleeRadius * A.Nerve * 1.35f)
	{
		A.Yaw = FMath::RadiansToDegrees(FMath::Atan2(-FromThreat.Y, -FromThreat.X));   // it looks at what frightened it
		Begin(A, EState::Start);
		return;
	}
	switch (A.State)
	{
	case EState::Start:
		if (A.StateTime >= A.StateDuration) { Begin(A, EState::Flee); }
		break;
	case EState::Flee:
	{
		if (A.StateTime >= A.StateDuration && (!H.bAlarmed || ThreatDist > F.WildlifeFleeRadius * 2.2f))
		{
			Begin(A, EState::Look);
			break;
		}
		// away from the threat, each on its own line, drawn a little toward the herd so it stays one
		FVector2D Want = FromThreat.GetSafeNormal().GetRotated(A.Veer) + (H.Centre - A.Pos).GetSafeNormal() * 0.25f;
		Want = Want.GetSafeNormal();
		if (Want.IsNearlyZero()) { Want = FVector2D(FMath::Cos(FMath::DegreesToRadians(A.Yaw)), FMath::Sin(FMath::DegreesToRadians(A.Yaw))); }
		const float Dist = F.WildlifeRunSpeed * (0.9f + 0.1f * A.Nerve) * Dt;
		static const float Turns[] = { 0.f, 30.f, -30.f, 60.f, -60.f, 95.f, -95.f, 135.f, -135.f };
		for (float Turn : Turns)
		{
			const FVector2D Dir = Want.GetRotated(Turn);
			if (Step(A, Dir, Dist))
			{
				const float WantYaw = FMath::RadiansToDegrees(FMath::Atan2(Dir.Y, Dir.X));
				A.Yaw = FMath::FixedTurn(A.Yaw, WantYaw, 540.f * Dt);
				A.Distance += Dist;
				break;
			}
		}
		break;
	}
	case EState::Walk:
	{
		const FVector2D To = A.Goal - A.Pos;
		const float Left = To.Size();
		const float Dist = F.WildlifeWalkSpeed * Dt;
		if (Left < 40.f || A.StateTime >= A.StateDuration || !Step(A, To / FMath::Max(Left, 1.f), FMath::Min(Dist, Left)))
		{
			Begin(A, Rng.FRand() < 0.7f ? EState::Graze : EState::Stand);
			break;
		}
		A.Yaw = FMath::FixedTurn(A.Yaw, FMath::RadiansToDegrees(FMath::Atan2(To.Y, To.X)), 200.f * Dt);
		A.Distance += Dist;
		break;
	}
	default:
		if (A.StateTime >= A.StateDuration)
		{
			// too far from the herd, or the herd has moved on: follow; otherwise graze, stand, look or stroll
			const float Away = FVector2D::Distance(A.Pos, H.Centre);
			const float Roll = Rng.FRand();
			if (Away > H.Spread || Roll < 0.3f)
			{
				for (int32 Try = 0; Try < 8; ++Try)
				{
					const float Ang = Rng.FRandRange(0.f, 2.f * PI);
					const FVector2D P = H.Centre + FVector2D(FMath::Cos(Ang), FMath::Sin(Ang)) * Rng.FRandRange(80.f, H.Spread * 0.85f);
					if (GoodGround(P, false)) { A.Goal = P; Begin(A, EState::Walk); break; }
				}
				if (A.State != EState::Walk) { Begin(A, EState::Stand); }
			}
			else if (Roll < 0.42f) { Begin(A, EState::Look); }
			else if (Roll < 0.6f) { Begin(A, EState::Stand); }
			else { Begin(A, EState::Graze); }
		}
		break;
	}
}

void ASRWildlife::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (!bReady)
	{
		RetryTimer -= DeltaSeconds;
		if (RetryTimer > 0.f) { return; }
		RetryTimer = 0.5f;
		bReady = Init();
		if (!bReady) { return; }
	}
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	const USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	if (!Battle || !Grid || Animals.Num() == 0) { return; }
	const float Dt = FMath::Min(DeltaSeconds, 0.1f);

	// ---- each herd: who is near, and where it drifts to next
	for (int32 h = 0; h < Herds.Num(); ++h)
	{
		FHerd& H = Herds[h];
		H.CalmTime += Dt;
		H.ScanTimer -= Dt;
		if (H.ScanTimer <= 0.f)
		{
			H.ScanTimer = 0.25f;
			// the nearest troop to any of the herd
			float Best = FMath::Square(F.WildlifeFleeRadius * 1.2f);
			bool bNear = false;
			for (const ASRUnit* U : Battle->GetUnits())
			{
				if (!U || !U->IsAlive()) { continue; }
				const FVector2D P = U->GetPos2D();
				if (FVector2D::DistSquared(P, H.Centre) > FMath::Square(F.WildlifeFleeRadius * 2.5f + H.Spread + 3000.f)) { continue; }
				for (const FAnimal& A : Animals)
				{
					if (A.Herd != h) { continue; }
					const float D2 = FVector2D::DistSquared(P, A.Pos);
					if (D2 < Best && D2 < FMath::Square(F.WildlifeFleeRadius * A.Nerve)) { Best = D2; H.Threat = P; bNear = true; }
				}
			}
			if (bNear) { H.bAlarmed = true; H.CalmTime = 0.f; }
			else if (H.bAlarmed && H.CalmTime > 2.5f)
			{
				// left alone: the herd is wherever it ran to
				H.bAlarmed = false;
				FVector2D Sum = FVector2D::ZeroVector;
				int32 N = 0;
				for (const FAnimal& A : Animals) { if (A.Herd == h) { Sum += A.Pos; ++N; } }
				if (N > 0)
				{
					const FVector2D Mid = Grid->NearestWalkable(Sum / float(N));
					if (GoodGround(Mid, false)) { H.Centre = Mid; }
				}
				H.DriftTimer = Rng.FRandRange(40.f, 90.f);
			}
		}
		if (H.bAlarmed)
		{
			// while it runs the herd's middle runs with it (so the stragglers are drawn after the leaders)
			FVector2D Sum = FVector2D::ZeroVector;
			int32 N = 0;
			for (const FAnimal& A : Animals) { if (A.Herd == h) { Sum += A.Pos; ++N; } }
			if (N > 0) { H.Centre = Sum / float(N); }
			continue;
		}
		H.DriftTimer -= Dt;
		if (H.DriftTimer <= 0.f)
		{
			H.DriftTimer = Rng.FRandRange(35.f, 90.f);
			for (int32 Try = 0; Try < 12; ++Try)
			{
				const float Ang = Rng.FRandRange(0.f, 2.f * PI);
				const FVector2D P = H.Centre + FVector2D(FMath::Cos(Ang), FMath::Sin(Ang)) * Rng.FRandRange(700.f, 1800.f);
				if (GoodGround(P, true) && Grid->CanWalkStraight(H.Centre, P)) { H.Centre = P; break; }
			}
		}
	}

	for (FAnimal& A : Animals)
	{
		Think(A, Herds[A.Herd], Dt);
		float Z = A.Z;
		if (Battle->SampleGround(A.Pos, A.Z + 80.f, Z)) { A.Z = Z; }
		Present(A, Dt);
	}
}

void ASRWildlife::Present(FAnimal& A, float Dt)
{
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	const FSRSpriteView& View = Battle->GetSpriteView();
	const USRFeelSettings& F = USRFeelSettings::Get();
	const USRFogSubsystem* Fog = USRFogSubsystem::Get(this);
	const bool bInView = FVector2D::DistSquared(A.Pos, View.FocusXY) <= FMath::Square(View.CullRadius);
	const bool bShown = bInView && (!Fog || !Fog->IsEnabled() || Fog->IsVisible(A.Pos));
	if (!bShown)
	{
		if (A.Card->IsVisible()) { A.Card->SetVisibility(false); A.ShadowCard->SetCastShadow(false); A.Applied = FVector4(-1.f, -1.f, -1.f, -1.f); }
		return;
	}
	A.Facing = SRSprite::FacingIndexSticky(A.Facing, A.Yaw, View.ViewYaw, F.FacingHysteresisDeg);
	A.ShadowFacing = SRSprite::FacingIndexSticky(A.ShadowFacing, A.Yaw, View.SunYaw, F.FacingHysteresisDeg);

	int32 Col = StandCol, Row = StandRow;
	switch (A.State)
	{
	case EState::Graze: Col = GrazeCol + (FMath::FloorToInt(A.Clock * 4.f) % GrazeFrames); Row = GrazeRow; break;
	case EState::Stand: Col = StandCol + (FMath::FloorToInt(A.Clock * 5.f) % 8); Row = StandRow; break;
	case EState::Look: Col = LookCol + FMath::Min(FMath::FloorToInt(A.StateTime * 3.f), 7); Row = LookRow; break;
	case EState::Walk: Col = WalkCol + (FMath::FloorToInt(A.Distance / (WalkCycleCm * A.Scale) * 8.f) % 8); Row = WalkRow; break;
	case EState::Start: Col = StartCol + FMath::Min(FMath::FloorToInt(A.StateTime * 9.f), StartFrames - 1); Row = StartRow; break;
	case EState::Flee: Col = BoltCol + (FMath::FloorToInt(A.Distance / (BoltCycleCm * A.Scale) * 8.f) % 8); Row = BoltRow; break;
	}

	if (!A.Card->IsVisible()) { A.Card->SetVisibility(true); }
	A.ShadowCard->SetCastShadow(F.bSpriteShadows);
	const FVector4 Data(float(Col), float(Row + A.Facing), 0.f, 1.f);
	if (!Data.Equals(A.Applied, 0.001f))
	{
		A.Applied = Data;
		A.Card->SetCustomPrimitiveDataVector4(SRSprite::DataFrame, Data);
		A.ShadowCard->SetCustomPrimitiveDataVector4(SRSprite::DataFrame, FVector4(float(Col), float(Row + A.ShadowFacing), 0.f, 1.f));
	}
	const FVector At(A.Pos.X, A.Pos.Y, A.Z);
	A.Card->SetWorldLocationAndRotation(At, View.CardRotation);
	A.ShadowCard->SetWorldLocationAndRotation(At + FVector(0.f, 0.f, 1.f), View.ShadowRotation);
	A.ShadowCard->SetWorldScale3D(View.ShadowScale * A.Scale);
}
