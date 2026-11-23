#include "VLBattle.h"
#include "SovereignRealms.h"
#include "VLEnemyAI.h"
#include "VLKing.h"
#include "VLTroop.h"
#include "VLGrid.h"
#include "VLCommand.h"
#include "VLArrow.h"
#include "VLSwordsmanCombat.h"
#include "VLArcherCombat.h"
#include "VLCharacterData.h"
#include "VLConstruction.h"
#include "VLMatchLog.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/PlayerStart.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundBase.h"
#include "Misc/PackageName.h"

// ------------------------------------------------------------------------------------------------ the rules

namespace VLRules
{
	EVLUnitKind KindOf(const FString& Kind)
	{
		// (the order the name compares had; a name of none of them: a swordsman's rules, but not the name)
		if (Kind == TEXT("Archer")) { return EVLUnitKind::Archer; }
		if (Kind == TEXT("Spy")) { return EVLUnitKind::Spy; }
		if (Kind == TEXT("Builder")) { return EVLUnitKind::Builder; }
		if (Kind == TEXT("King")) { return EVLUnitKind::King; }
		return Kind == TEXT("Swordsman") ? EVLUnitKind::Swordsman : EVLUnitKind::Other;
	}

	const FTroop& Troop(const FString& Kind)
	{
		return Troop(KindOf(Kind));
	}

	const FTroop& Troop(EVLUnitKind Kind)
	{
		// The main game: Shieldbearer 280 hp, 27 a blow every 1.15 s, 100 food, 9 s; Archer 125 hp, 18 an arrow every
		// 1.5 s, 0.35x against buildings, 85 food, 8 s. Per hit here x1.25/1.15 and x2.4/1.5: the same damage a second.
		// Sight is the main game's 13 m / 15 m plus 30% (the user's call): 16.9 m / 19.5 m. What they notice and go
		// for (Acquire) is much further, 40 m / 42 m (about 2.4x / 2.15x: the owner's call, 2026-11-22, troops stood by
		// while a fight went on just ahead of them); the stances still hold them (UVLBattle::TickAutoCombat). The
		// archer's arrow is 40 (was 29, the main game's damage a second): +38%, so archers are worth fielding; a
		// swordsman still wins up close (23 damage a second against 17, 280 health against 125).
		// Every time here is twice the main game's (the owner's call, 2026-11-22: "if something takes 30 seconds, it
		// should take 1 minute"): training 18 / 16 s (was 9 / 8), the Spy 24 s, the Builder 28 s; so are the levels'
		// times below and the sites' (VLBuild::Specs; the watch tower three times).
		static const FTroop Sword = [] { FTroop T; T.Health = 280.f; T.Damage = 29.f; T.BuildingScale = 1.f; T.Acquire = 4000.f; T.Sight = 1690.f; T.Pop = 1; T.Cost.Food = 100; T.TrainSeconds = 18.f; return T; }();
		static const FTroop Bow = [] { FTroop T; T.Health = 125.f; T.Damage = 40.f; T.BuildingScale = 0.5f; T.Acquire = 4200.f; T.Sight = 1950.f; T.Pop = 1; T.Cost.Food = 85; T.TrainSeconds = 16.f; return T; }();
		// King David: the hero (the main game had none). Worth two swordsmen and a half; he takes no housing. His pace
		// is a troop's, 420 / 760 cm/s (the owner's call, 2026-11-22: he walks with his men; it was 520 / 950).
		static const FTroop King = [] { FTroop T; T.Health = 600.f; T.Damage = 45.f; T.BuildingScale = 1.f; T.Acquire = 4000.f; T.Sight = 1690.f; T.Pop = 0; T.TrainSeconds = 0.f;
			T.WalkSpeed = 420.f; T.RunSpeed = 760.f; return T; }();
		// The Spy (the main game's Scout): 90 hp, 8 a blow every 1.2 s (x0.2 against buildings), picks no fights (no
		// acquire range), sees 26 m, noticed at 45% of the usual distance, 875 cm/s (a Shieldbearer did 450: 1.94x),
		// 350 gold + 200 food, 12 s at the castle.
		static const FTroop Spy = [] { FTroop T; T.Health = 90.f; T.Damage = 8.f; T.BuildingScale = 0.2f; T.Acquire = 0.f; T.Pop = 1; T.Cost.Gold = 350; T.Cost.Food = 200;
			T.TrainSeconds = 24.f; T.Sight = 3380.f; T.Notice = 0.45f; T.WalkSpeed = 875.f; T.RunSpeed = 1100.f; return T; }();
		if (Kind == EVLUnitKind::Archer)
		{
			return Bow;
		}
		if (Kind == EVLUnitKind::Spy)
		{
			return Spy;
		}
		// The Builder (the main game's): no fighter (no acquire range; its hammer swings at its work, or when the player
		// plays one). 110 hp, 6 a blow every 1.3 s (here 8 a swing, x0.5 against buildings), 120 gold + 80 food, 14 s at
		// the castle; no housing: its own limit is the castle's level (VLBuild::MaxBuilders). It raises and repairs
		// buildings (VLConstruction.*).
		static const FTroop Builder = [] { FTroop T; T.Health = 110.f; T.Damage = 8.f; T.BuildingScale = 0.5f; T.Acquire = 0.f; T.Sight = 1690.f; T.Pop = 0; T.Cost.Gold = 120; T.Cost.Food = 80;
			T.TrainSeconds = 28.f; return T; }();
		if (Kind == EVLUnitKind::Builder)
		{
			return Builder;
		}
		return Kind == EVLUnitKind::King ? King : Sword;
	}

	namespace
	{
		FLevel Make(int32 G, int32 F, float Sec, float Hp)
		{
			FLevel L;
			L.Cost.Gold = G;
			L.Cost.Food = F;
			L.Seconds = Sec;
			L.Health = Hp;
			return L;
		}

		struct FTables
		{
			TArray<FLevel> Castle, Tower, Farm, Mine, Barracks, Range, Granary, Treasury, Hall;
			FTables()
			{
				// the Citadel (FSRCastleLevel): price, time, housing, troop ceiling, walls, stores, archers, arrow
				struct { int32 G, F; float S; int32 H, C; float Hp; int32 St, A; float D; } C[7] = {
					{ 0, 0, 0.f, 8, 36, 12000.f, 600, 1, 36.f }, { 300, 0, 80.f, 16, 48, 15000.f, 1000, 2, 36.f }, { 550, 150, 90.f, 24, 60, 18000.f, 1500, 2, 40.f },
					{ 850, 300, 110.f, 32, 75, 21000.f, 2200, 3, 40.f }, { 1200, 450, 130.f, 42, 90, 24000.f, 3000, 3, 44.f }, { 1650, 650, 150.f, 52, 105, 27000.f, 4000, 4, 44.f },
					{ 2200, 900, 180.f, 64, 120, 30000.f, 5500, 4, 48.f } };
				for (const auto& X : C)
				{
					FLevel L = Make(X.G, X.F, X.S, X.Hp);
					L.Housing = X.H; L.Ceiling = X.C; L.Storage = X.St; L.Archers = X.A; L.Damage = X.D; L.Interval = 1.4f; L.Range = 1000.f;
					Castle.Add(L);
				}
				// the Watchtower: 50 / 85 / 120 damage every 1.2 / 0.95 / 0.8 s, reach 24 / 27 / 30 m
				struct { int32 G; float S, D, I, R, Hp; } T[3] = { { 0, 0.f, 35.f, 1.2f, 2400.f, 1800.f }, { 250, 60.f, 60.f, 0.95f, 2700.f, 2300.f }, { 370, 80.f, 85.f, 0.8f, 3000.f, 2800.f } };
				for (const auto& X : T)
				{
					FLevel L = Make(X.G, 0, X.S, X.Hp);
					L.Archers = 1; L.Damage = X.D; L.Interval = X.I; L.Range = X.R;
					Tower.Add(L);
				}
				// farms: food a harvest and housing; mines: gold a delivery
				struct { int32 G, F; float S; int32 Y, H; float Hp; } Fa[3] = { { 0, 0, 0.f, 14, 4, 1000.f }, { 200, 0, 60.f, 20, 6, 1300.f }, { 340, 60, 80.f, 27, 8, 1600.f } };
				for (const auto& X : Fa)
				{
					FLevel L = Make(X.G, X.F, X.S, X.Hp);
					L.Yield = X.Y; L.Housing = X.H;
					Farm.Add(L);
				}
				struct { int32 G, F; float S; int32 Y; float Hp; } Mi[3] = { { 0, 0, 0.f, 10, 1250.f }, { 220, 0, 60.f, 16, 1600.f }, { 360, 100, 80.f, 23, 2000.f } };
				for (const auto& X : Mi)
				{
					FLevel L = Make(X.G, X.F, X.S, X.Hp);
					L.Yield = X.Y;
					Mine.Add(L);
				}
				// the barracks and the range (FSRTrainerLevel): faster training, sturdier walls (x1, x1.2, x1.4)
				struct { int32 G, F; float S, Speed, Scale; } Tr[3] = { { 0, 0, 0.f, 1.f, 1.f }, { 200, 100, 60.f, 1.35f, 1.2f }, { 380, 180, 80.f, 1.8f, 1.4f } };
				for (const auto& X : Tr)
				{
					FLevel B = Make(X.G, X.F, X.S, 1600.f * X.Scale);
					B.TrainSpeed = X.Speed;
					Barracks.Add(B);
					FLevel R = Make(X.G, X.F, X.S, 1400.f * X.Scale);
					R.TrainSpeed = X.Speed;
					Range.Add(R);
				}
				// storehouses (FSRStoreLevel): what they hold on top of the castle's stores
				struct { int32 G, F; float S; int32 Cap; float Hp; int32 Castle; } Gr[3] = { { 0, 0, 0.f, 400, 900.f, 0 }, { 180, 0, 60.f, 900, 1200.f, 2 }, { 320, 80, 80.f, 1600, 1500.f, 3 } };
				struct { int32 G, F; float S; int32 Cap; float Hp; int32 Castle; } Te[3] = { { 0, 0, 0.f, 400, 1100.f, 0 }, { 200, 0, 60.f, 900, 1450.f, 2 }, { 340, 80, 80.f, 1600, 1800.f, 3 } };
				for (int32 i = 0; i < 3; ++i)
				{
					FLevel G = Make(Gr[i].G, Gr[i].F, Gr[i].S, Gr[i].Hp);
					G.Storage = Gr[i].Cap; G.CastleLevel = Gr[i].Castle;
					Granary.Add(G);
					FLevel Tz = Make(Te[i].G, Te[i].F, Te[i].S, Te[i].Hp);
					Tz.Storage = Te[i].Cap; Tz.CastleLevel = Te[i].Castle;
					Treasury.Add(Tz);
				}
				Hall.Add(Make(0, 0, 0.f, 1500.f));
			}
			const TArray<FLevel>& Of(EVLBuilding Kind) const
			{
				switch (Kind)
				{
				case EVLBuilding::Castle: return Castle;
				case EVLBuilding::Tower: return Tower;
				case EVLBuilding::Farm: return Farm;
				case EVLBuilding::Mine: return Mine;
				case EVLBuilding::Barracks: return Barracks;
				case EVLBuilding::Range: return Range;
				case EVLBuilding::Granary: return Granary;
				case EVLBuilding::Treasury: return Treasury;
				default: return Hall;
				}
			}
		};

		const FTables& Tables()
		{
			static const FTables T;
			return T;
		}
	}

	int32 NumLevels(EVLBuilding Kind)
	{
		return Tables().Of(Kind).Num();
	}

	const FLevel& Level(EVLBuilding Kind, int32 InLevel)
	{
		const TArray<FLevel>& L = Tables().Of(Kind);
		return L[FMath::Clamp(InLevel - 1, 0, L.Num() - 1)];
	}

	const TCHAR* Name(EVLBuilding Kind)
	{
		switch (Kind)
		{
		case EVLBuilding::Castle: return TEXT("Castle");
		case EVLBuilding::Barracks: return TEXT("Barracks");
		case EVLBuilding::Range: return TEXT("Archery Range");
		case EVLBuilding::Farm: return TEXT("Farm");
		case EVLBuilding::Mine: return TEXT("Gold Mine");
		case EVLBuilding::Tower: return TEXT("Watch Tower");
		case EVLBuilding::Granary: return TEXT("Granary");
		case EVLBuilding::Treasury: return TEXT("Treasury");
		case EVLBuilding::Hall: return TEXT("Town Hall");
		default: return TEXT("-");
		}
	}

	EVLBuilding KindFromName(const FString& N)
	{
		if (N.Equals(TEXT("Castle"), ESearchCase::IgnoreCase) || N.Equals(TEXT("Citadel"), ESearchCase::IgnoreCase)) { return EVLBuilding::Castle; }
		if (N.Equals(TEXT("Barracks"), ESearchCase::IgnoreCase)) { return EVLBuilding::Barracks; }
		if (N.Equals(TEXT("Archery Range"), ESearchCase::IgnoreCase) || N.Equals(TEXT("Range"), ESearchCase::IgnoreCase)) { return EVLBuilding::Range; }
		if (N.StartsWith(TEXT("Farm"), ESearchCase::IgnoreCase)) { return EVLBuilding::Farm; }
		if (N.Equals(TEXT("Gold Mine"), ESearchCase::IgnoreCase) || N.Equals(TEXT("Mine"), ESearchCase::IgnoreCase)) { return EVLBuilding::Mine; }
		if (N.Equals(TEXT("Watch Tower"), ESearchCase::IgnoreCase) || N.Equals(TEXT("Watchtower"), ESearchCase::IgnoreCase) || N.Equals(TEXT("Tower"), ESearchCase::IgnoreCase)) { return EVLBuilding::Tower; }
		if (N.Equals(TEXT("Granary"), ESearchCase::IgnoreCase)) { return EVLBuilding::Granary; }
		if (N.Equals(TEXT("Treasury"), ESearchCase::IgnoreCase)) { return EVLBuilding::Treasury; }
		if (N.Equals(TEXT("Town Hall"), ESearchCase::IgnoreCase)) { return EVLBuilding::Hall; }
		return EVLBuilding::None;
	}
}

// ------------------------------------------------------------------------------------------------ helpers

namespace
{
	TAutoConsoleVariable<int32> CVarAIvsAIKing(TEXT("vl.AIvsAI.King"), 0, TEXT("1: with vl.AIvsAI, King David stays in the match (he fights by himself near his castle); 0 (default): he is benched"));
	TAutoConsoleVariable<int32> CVarBattleLog(TEXT("vl.BattleLog"), 0, TEXT("1: log every hit on a unit or a building, every engagement and every death"));

	bool BattleLog()
	{
		return CVarBattleLog.GetValueOnGameThread() != 0;
	}

	FString TagValue(const AActor* A, const TCHAR* Prefix)
	{
		if (!A)
		{
			return FString();
		}
		const int32 Len = FCString::Strlen(Prefix);
		for (const FName& Tag : A->Tags)
		{
			const FString S = Tag.ToString();
			if (S.StartsWith(Prefix))
			{
				return S.Mid(Len);
			}
		}
		return FString();
	}

	/** The building's box: its first static mesh's bounds, in that component's space. */
	bool BoxOf(const AActor* A, FTransform& OutT, FBox& OutLocal)
	{
		const UStaticMeshComponent* SMC = A ? A->FindComponentByClass<UStaticMeshComponent>() : nullptr;
		if (!SMC || !SMC->GetStaticMesh())
		{
			return false;
		}
		OutT = SMC->GetComponentTransform();
		OutLocal = SMC->GetStaticMesh()->GetBoundingBox();
		return true;
	}

	/** Who dealt a blow, for the match's books (FVLKingdom::DamageBy). */
	int32 StrikerClass(const AActor* By)
	{
		const AVLKing* K = Cast<AVLKing>(By);
		return K ? (K->bTowerGuard ? 6 : FMath::Min(int32(K->KindId()), 5)) : 7;
	}

	bool InPlayersHands(const AVLKing* U)
	{
		return U && Cast<APlayerController>(U->GetController()) && U->IsHeroMode();
	}

	AActor* CombatTarget(AVLKing* U, bool* bOutAttacking = nullptr)
	{
		AActor* T = nullptr;
		bool bAttacking = false;
		if (const UVLSwordsmanCombat* S = UVLSwordsmanCombat::For(U, false); S && S->IsAttacking())
		{
			T = S->GetTarget();
			bAttacking = true;
		}
		if (const UVLArcherCombat* A = UVLArcherCombat::For(U, false); A && A->IsAttacking())
		{
			T = T ? T : A->GetTarget();
			bAttacking = true;
		}
		if (bOutAttacking)
		{
			*bOutAttacking = bAttacking;
		}
		return T;
	}

	FString ClockText(float Seconds)
	{
		const int32 S = FMath::Max(0, FMath::CeilToInt(Seconds));
		return FString::Printf(TEXT("%d:%02d"), S / 60, S % 60);
	}
}

float UVLBattle::EffectsVolume = 1.f;

UVLBattle* UVLBattle::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UVLBattle>() : nullptr;
}

bool UVLBattle::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UVLBattle::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	// the unit registry: every unit there is now, and each one that comes or goes from here on
	SpawnedHandle = InWorld.AddOnActorSpawnedHandler(FOnActorSpawned::FDelegate::CreateUObject(this, &UVLBattle::OnActorSpawned));
	DestroyedHandle = InWorld.AddOnActorDestroyedHandler(FOnActorDestroyed::FDelegate::CreateUObject(this, &UVLBattle::OnActorDestroyed));
	Registered.Reset();
	for (TActorIterator<AVLKing> It(&InWorld); It; ++It)
	{
		if (!It->bAmbient)          // (a figure of the scenery, a farm's hand, is nobody's unit)
		{
			Registered.AddUnique(*It);
		}
	}
	bHashDirty = true;
	bTagsDirty = true;
	ScanBuildings();
	for (int32 t = 0; t < 2; ++t)
	{
		Commanders[t] = MakeShared<FVLCommander>();
		Kingdoms[t] = FVLKingdom();
		Kingdoms[t].Gold = VLRules::StartGold;
		Kingdoms[t].Food = VLRules::StartFood;
	}
	Pan = NewObject<USoundAttenuation>(this);
	Pan->Attenuation.bAttenuate = false;
	Pan->Attenuation.bSpatialize = true;
}

void UVLBattle::Deinitialize()
{
	if (const UWorld* World = GetWorld())
	{
		World->RemoveOnActorSpawnedHandler(SpawnedHandle);
		World->RemoveOnActorDestroyedHandler(DestroyedHandle);
	}
	Registered.Reset();
	Commanders[0].Reset();
	Commanders[1].Reset();
	Super::Deinitialize();
}

// ------------------------------------------------------------------------------------------------ the unit registry

namespace
{
	TAutoConsoleVariable<int32> CVarOptRegistry(TEXT("vl.Opt.Registry"), 1,
		TEXT("1: units come from the battle's registry and its spatial hash, buildings and tagged actors from cached lists; 0: the old walks over every actor (to compare)"));
	TAutoConsoleVariable<int32> CVarOptFoeScan(TEXT("vl.Opt.FoeScan"), 1,
		TEXT("1: a unit looking for a foe gathers only the other side's living from the spatial hash, and passes over a building whose bounds are further than the best so far (the same choice, sooner). 0: as it was"));
	TAutoConsoleVariable<int32> CVarOptRegistryCheck(TEXT("vl.Opt.RegistryCheck"), 0,
		TEXT("1: every frame, check the registry against a walk over every unit, and every unit's choice of foe by the hash against the choice by the full walk; differences are logged"));
}

bool FVLOptTiming::bOn = false;
double FVLOptTiming::Seconds[FVLOptTiming::Num] = {};
int32 FVLOptTiming::Calls[FVLOptTiming::Num] = {};

namespace
{
	FAutoConsoleCommand CmdOptTiming(TEXT("vl.Opt.Timing"), TEXT("log the milliseconds a frame the paths of the optimisation pass took since this was last asked (the first call starts the clocks)"),
		FConsoleCommandDelegate::CreateLambda([]
		{
			static uint64 Since = 0;
			static const TCHAR* Names[FVLOptTiming::Num] = { TEXT("AutoSteer"), TEXT("UVLBattle::Tick"), TEXT("TickAutoCombat"), TEXT("UVLArrows::Tick"), TEXT("HUD rings+pips+bars"),
				TEXT("TickShuffle"), TEXT("Ambience"), TEXT("minimap dots") };
			const int32 Frames = int32(GFrameCounter - Since);
			if (FVLOptTiming::bOn && Frames > 0)
			{
				FString Line;
				for (int32 i = 0; i < FVLOptTiming::Num; ++i)
				{
					Line += FString::Printf(TEXT("%s %.3f (%d calls/frame)%s"), Names[i], FVLOptTiming::Seconds[i] * 1000.0 / Frames, FVLOptTiming::Calls[i] / Frames, i + 1 < FVLOptTiming::Num ? TEXT(" | ") : TEXT(""));
				}
				UE_LOG(LogSovereignRealms, Log, TEXT("OptTiming over %d frames, ms a frame: %s"), Frames, *Line);
			}
			FVLOptTiming::bOn = true;
			Since = GFrameCounter;
			for (int32 i = 0; i < FVLOptTiming::Num; ++i)
			{
				FVLOptTiming::Seconds[i] = 0.0;
				FVLOptTiming::Calls[i] = 0;
			}
		}));
}

bool UVLBattle::UseRegistry()
{
	return CVarOptRegistry.GetValueOnGameThread() != 0;
}

void AVLKing::CacheKind() const
{
	CachedKind = VLRules::KindOf(UnitKind);
	CachedRules = &VLRules::Troop(CachedKind);
}

void UVLBattle::OnActorSpawned(AActor* Actor)
{
	if (AVLKing* Unit = Cast<AVLKing>(Actor))
	{
		if (!Unit->bAmbient)        // (a farm's hand: no side, never fought, selected or counted: AVLFarmer)
		{
			Registered.AddUnique(Unit);
			bHashDirty = true;
		}
	}
	else if (Actor && !Actor->IsA<AController>() && !Actor->IsA<AInfo>())
	{
		bTagsDirty = true;          // (its tags are given after it is spawned: read when next asked for)
	}
}

void UVLBattle::OnActorDestroyed(AActor* Actor)
{
	if (AVLKing* Unit = Cast<AVLKing>(Actor))
	{
		Registered.Remove(Unit);
		bHashDirty = true;
	}
}

const TArray<AVLKing*>& UVLBattle::AllUnits() const
{
	if (UseRegistry())
	{
		return Registered;
	}
	LegacyUnits.Reset();
	for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
	{
		if (!It->bAmbient)
		{
			LegacyUnits.Add(*It);
		}
	}
	return LegacyUnits;
}

void UVLBattle::GetAllUnits(FVLUnits& Out) const
{
	Out.Reset();
	Out.Append(AllUnits());
}

void UVLBattle::RefreshUnitHash() const
{
	bHashDirty = true;
	EnsureUnitHash();
}

void UVLBattle::EnsureUnitHash() const
{
	if (!bHashDirty && HashFrame == GFrameCounter)
	{
		return;
	}
	bHashDirty = false;
	HashFrame = GFrameCounter;
	const int32 N = Registered.Num();
	int32 Buckets = 64;
	while (Buckets < N * 2)
	{
		Buckets *= 2;
	}
	HashCells.SetNumUninitialized(N, EAllowShrinking::No);
	HashItems.SetNumUninitialized(N, EAllowShrinking::No);
	HashStart.Reset();
	HashStart.SetNumZeroed(Buckets + 1);
	HashMin = FIntPoint(MAX_int32, MAX_int32);
	HashMax = FIntPoint(MIN_int32, MIN_int32);
	auto Bucket = [Buckets](const FIntPoint& C) { return int32((uint32(C.X) * 73856093u ^ uint32(C.Y) * 19349663u) & uint32(Buckets - 1)); };
	for (int32 i = 0; i < N; ++i)
	{
		const FVector P = Registered[i]->GetActorLocation();
		const FIntPoint C(FMath::FloorToInt32(float(FMath::Clamp(P.X, -1.0e7, 1.0e7)) / UnitCell), FMath::FloorToInt32(float(FMath::Clamp(P.Y, -1.0e7, 1.0e7)) / UnitCell));
		HashCells[i] = C;
		HashMin = FIntPoint(FMath::Min(HashMin.X, C.X), FMath::Min(HashMin.Y, C.Y));
		HashMax = FIntPoint(FMath::Max(HashMax.X, C.X), FMath::Max(HashMax.Y, C.Y));
		++HashStart[Bucket(C) + 1];
	}
	for (int32 b = 0; b < Buckets; ++b)
	{
		HashStart[b + 1] += HashStart[b];
	}
	// (filled in registry order: each bucket's units ascend)
	TArray<int32, TInlineAllocator<1024>> Fill;
	Fill.Append(HashStart.GetData(), Buckets);
	for (int32 i = 0; i < N; ++i)
	{
		HashItems[Fill[Bucket(HashCells[i])]++] = i;
	}
}

void UVLBattle::UnitsInBox(const FVector2D& Min, const FVector2D& Max, FVLUnits& Out, int32 NotOfTeam) const
{
	Out.Reset();
	if (!UseRegistry())
	{
		Out.Append(AllUnits());
		return;
	}
	// (NotOfTeam: a caller looking for foes; one of that side, of no side or dead is not gathered)
	const bool bFoesOnly = NotOfTeam != MIN_int32;
	auto Wanted = [NotOfTeam](const AVLKing* K) { return K->Team != NotOfTeam && K->Team >= 0 && K->IsAlive(); };
	EnsureUnitHash();
	const int32 N = Registered.Num();
	if (N == 0)
	{
		return;
	}
	// how far a unit may have gone since the hash was made (this frame's own move), and a little more
	const UWorld* World = GetWorld();
	const double Slack = 60.0 + 3000.0 * (World ? FMath::Min(World->GetDeltaSeconds(), 0.5f) : 0.05f);
	const int32 X0 = FMath::Max(FMath::FloorToInt32(float(FMath::Clamp(Min.X - Slack, -1.0e7, 1.0e7)) / UnitCell), HashMin.X);
	const int32 Y0 = FMath::Max(FMath::FloorToInt32(float(FMath::Clamp(Min.Y - Slack, -1.0e7, 1.0e7)) / UnitCell), HashMin.Y);
	const int32 X1 = FMath::Min(FMath::FloorToInt32(float(FMath::Clamp(Max.X + Slack, -1.0e7, 1.0e7)) / UnitCell), HashMax.X);
	const int32 Y1 = FMath::Min(FMath::FloorToInt32(float(FMath::Clamp(Max.Y + Slack, -1.0e7, 1.0e7)) / UnitCell), HashMax.Y);
	if (X1 < X0 || Y1 < Y0)
	{
		return;
	}
	if (int64(X1 - X0 + 1) * int64(Y1 - Y0 + 1) > int64(N) * 2 + 16)
	{
		// (a wide look: the walk over every unit is the shorter one)
		if (!bFoesOnly)
		{
			Out.Append(Registered);
			return;
		}
		for (AVLKing* K : Registered)
		{
			if (Wanted(K))
			{
				Out.Add(K);
			}
		}
		return;
	}
	const uint32 Mask = uint32(HashStart.Num() - 2);
	TArray<int32, TInlineAllocator<128>> Found;
	for (int32 Y = Y0; Y <= Y1; ++Y)
	{
		for (int32 X = X0; X <= X1; ++X)
		{
			const int32 B = int32((uint32(X) * 73856093u ^ uint32(Y) * 19349663u) & Mask);
			for (int32 k = HashStart[B]; k < HashStart[B + 1]; ++k)
			{
				const int32 i = HashItems[k];
				if (HashCells[i].X == X && HashCells[i].Y == Y && (!bFoesOnly || Wanted(Registered[i])))
				{
					Found.Add(i);
				}
			}
		}
	}
	Found.Sort();
	Out.Reserve(Found.Num());
	for (const int32 i : Found)
	{
		Out.Add(Registered[i]);
	}
}

void UVLBattle::UnitsNear(const FVector& At, float Radius, FVLUnits& Out) const
{
	UnitsInBox(FVector2D(At.X - Radius, At.Y - Radius), FVector2D(At.X + Radius, At.Y + Radius), Out);
}

void UVLBattle::EnsureTags() const
{
	const UWorld* World = GetWorld();
	const double Now = World ? World->GetRealTimeSeconds() : 0.0;
	if (!bTagsDirty && Now - TagsReadAt < 1.0)
	{
		return;
	}
	bTagsDirty = false;
	TagsReadAt = Now;
	SelectableActors.Reset();
	DummyActors.Reset();
	MineNamedActors.Reset();
	static const FName Selectable(TEXT("Selectable")), Dummy(TEXT("Dummy"));
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* A = *It;
		if (A->Tags.Num() == 0)
		{
			continue;
		}
		if (A->Tags.Contains(Selectable) && !A->IsA<AVLKing>())
		{
			SelectableActors.Add(A);
		}
		if (A->Tags.Contains(Dummy))
		{
			DummyActors.Add(A);
		}
		if (VLRules::KindFromName(TagValue(A, TEXT("Name:"))) == EVLBuilding::Mine)
		{
			MineNamedActors.Add(A);
		}
	}
}

const TArray<TWeakObjectPtr<AActor>>& UVLBattle::Selectables() const
{
	EnsureTags();
	return SelectableActors;
}

const TArray<TWeakObjectPtr<AActor>>& UVLBattle::Dummies() const
{
	EnsureTags();
	return DummyActors;
}

const TArray<TWeakObjectPtr<AActor>>& UVLBattle::MineActors() const
{
	EnsureTags();
	return MineNamedActors;
}

void UVLBattle::CheckRegistry()
{
	// the registry against the world
	TArray<AVLKing*> World;
	for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
	{
		if (!It->bAmbient)
		{
			World.Add(*It);
		}
	}
	int32 Missing = 0;
	for (AVLKing* U : World)
	{
		Missing += Registered.Contains(U) ? 0 : 1;
	}
	if (Missing > 0 || World.Num() != Registered.Num())
	{
		UE_LOG(LogSovereignRealms, Warning, TEXT("registry check: %d unit(s) in the world, %d registered, %d missing"), World.Num(), Registered.Num(), Missing);
	}
	// every unit's foe: by the hash, and by the walk over every unit (the same order)
	int32 Asked = 0, Differ = 0;
	for (AVLKing* U : Registered)
	{
		if (!U->IsAlive() || U->Team < 0)
		{
			continue;
		}
		const float Range = U->KindRules().Acquire > 0.f ? U->KindRules().Acquire : 1690.f;
		AActor* ByHash = FindFoe(U, Range, true);
		AActor* ByWalk = FindFoeIn(U, Range, true, Registered);
		AActor* ByOld = FindFoeIn(U, Range, true, World);
		++Asked;
		if (ByHash != ByWalk || ByHash != ByOld)
		{
			++Differ;
			UE_LOG(LogSovereignRealms, Warning, TEXT("registry check: %s would go for %s by the hash, %s by the registry walk, %s by the actor walk"), *U->GetDisplayName(),
				*GetNameSafe(ByHash), *GetNameSafe(ByWalk), *GetNameSafe(ByOld));
		}
	}
	static int32 Frames = 0, Total = 0, Bad = 0;
	Total += Asked;
	Bad += Differ;
	if (++Frames % 300 == 0)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("registry check: %d frames, %d foe choices compared, %d differed; %d units, %d selectable, %d dummies"), Frames, Total, Bad, Registered.Num(),
			Selectables().Num(), Dummies().Num());
	}
}

// ------------------------------------------------------------------------------------------------ teams

int32 UVLBattle::TeamOf(const AActor* Actor) const
{
	if (const AVLKing* U = Cast<AVLKing>(Actor))
	{
		return U->Team;
	}
	if (const FVLBuildingState* B = FindBuilding(Actor))
	{
		return B->Team;
	}
	return Neutral;
}

bool UVLBattle::IsAlive(const AActor* Actor) const
{
	if (!IsValid(Actor))
	{
		return false;
	}
	if (const AVLKing* U = Cast<AVLKing>(Actor))
	{
		return U->IsAlive();
	}
	const FVLBuildingState* B = FindBuilding(Actor);
	return !B || B->IsAlive();
}

bool UVLBattle::IsHostile(const AActor* Actor, int32 Team) const
{
	const int32 T = TeamOf(Actor);
	return T != Neutral && T != Team && Team != Neutral && IsAlive(Actor);
}

FLinearColor UVLBattle::TeamColour(int32 Team)
{
	// the main game's PlayerTeamColor / EnemyTeamColor, a little lighter to read on the grass
	return Team == Player ? FLinearColor(0.22f, 0.48f, 1.f) : (Team == Enemy ? FLinearColor(0.95f, 0.18f, 0.12f) : FLinearColor(0.8f, 0.8f, 0.8f));
}

const TCHAR* UVLBattle::TeamName(int32 Team)
{
	return Team == Player ? TEXT("yours") : (Team == Enemy ? TEXT("the enemy's") : TEXT("neutral"));
}

// ------------------------------------------------------------------------------------------------ buildings

void UVLBattle::ScanBuildings()
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (!It->IsA<AVLKing>() && (It->ActorHasTag(TEXT("Selectable")) || !TagValue(*It, TEXT("Team:")).IsEmpty()))
		{
			RegisterBuilding(*It);
		}
	}
	int32 N[2] = { 0, 0 };
	for (const FVLBuildingState& B : Buildings)
	{
		if (B.Team >= 0)
		{
			++N[B.Team];
		}
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("battle: %d buildings (%d the player's, %d the enemy's)"), Buildings.Num(), N[0], N[1]);
}

void UVLBattle::RegisterBuilding(AActor* Actor)
{
	if (!Actor)
	{
		return;
	}
	const FString Name = TagValue(Actor, TEXT("Name:"));
	const FString TeamTag = TagValue(Actor, TEXT("Team:"));
	EVLBuilding Kind = VLRules::KindFromName(Name);
	int32 Team = Kind != EVLBuilding::None ? Player : Neutral;      // (a game building with no Team tag: the player's, as in the sandboxes)
	if (!TeamTag.IsEmpty())
	{
		Team = TeamTag.IsNumeric() ? FMath::Clamp(FCString::Atoi(*TeamTag), 0, 1) : Neutral;
	}
	// (something of a side's that is no building of the game, a banner, a dock: not a building of the battle)
	FVLBuildingState* B = FindBuilding(Actor);
	if (Kind == EVLBuilding::None || Team == Neutral)
	{
		if (B)
		{
			B->Team = Neutral;
		}
		return;
	}
	if (!B)
	{
		B = &Buildings.AddDefaulted_GetRef();
		bBuildingIndexDirty = true;
		bTagsDirty = true;
		B->Actor = Actor;
		B->Rest = Actor->GetActorLocation();
		B->Payout = FMath::FRandRange(0.f, VLRules::PayoutInterval);
	}
	B->Kind = Kind;
	B->Team = Team;
	B->Name = Name.IsEmpty() ? VLRules::Name(Kind) : Name;
	ApplyLevel(*B, true);
}

FVLBuildingState* UVLBattle::FindBuilding(const AActor* Actor)
{
	if (!Actor)
	{
		return nullptr;
	}
	if (UseRegistry())
	{
		// by the index (made again when the array changes); a unit is never a building
		if (bBuildingIndexDirty || BuildingIndex.Num() > Buildings.Num())
		{
			bBuildingIndexDirty = false;
			BuildingIndex.Reset();
			for (int32 i = 0; i < Buildings.Num(); ++i)
			{
				if (const AActor* A = Buildings[i].Actor.Get(); A && !BuildingIndex.Contains(A))
				{
					BuildingIndex.Add(A, i);        // (the first of an actor, as the walk finds it)
				}
			}
		}
		const int32* Index = BuildingIndex.Find(Actor);
		if (!Index)
		{
			return nullptr;
		}
		if (Buildings.IsValidIndex(*Index) && Buildings[*Index].Actor.Get() == Actor)
		{
			return &Buildings[*Index];
		}
		bBuildingIndexDirty = true;         // (stale: an actor gone and another in its place; the walk below decides)
	}
	for (FVLBuildingState& B : Buildings)
	{
		if (B.Actor.Get() == Actor)
		{
			return &B;
		}
	}
	return nullptr;
}

const FVLBuildingState* UVLBattle::FindBuilding(const AActor* Actor) const
{
	return const_cast<UVLBattle*>(this)->FindBuilding(Actor);
}

AActor* UVLBattle::GetCastle(int32 Team) const
{
	for (const FVLBuildingState& B : Buildings)
	{
		if (B.Kind == EVLBuilding::Castle && B.Team == Team && B.IsAlive())
		{
			return B.Actor.Get();
		}
	}
	return nullptr;
}

int32 UVLBattle::CountBuildings(EVLBuilding Kind, int32 Team) const
{
	int32 N = 0;
	for (const FVLBuildingState& B : Buildings)
	{
		N += (B.Kind == Kind && B.Team == Team && B.IsAlive()) ? 1 : 0;
	}
	return N;
}

void UVLBattle::ApplyLevel(FVLBuildingState& B, bool bFull)
{
	const float Old = B.MaxHealth;
	B.MaxHealth = VLRules::Level(B.Kind, B.Level).Health;
	B.Health = bFull ? B.MaxHealth : FMath::Clamp(B.Health + (B.MaxHealth - Old), 1.f, B.MaxHealth);
}

float UVLBattle::DistanceTo(const AActor* Target, const FVector& From, FVector* OutPoint) const
{
	if (!Target)
	{
		return TNumericLimits<float>::Max();
	}
	if (const AVLKing* U = Cast<AVLKing>(Target))
	{
		const FVector F = U->GetFeet();
		if (OutPoint)
		{
			*OutPoint = F;
		}
		return FVector::Dist2D(F, From);
	}
	FTransform T;
	FBox Local;
	if (FindBuilding(Target) && BoxOf(Target, T, Local))
	{
		// the closest point of its turned box, on the ground plane
		FVector L = T.InverseTransformPosition(From);
		const bool bInside = L.X > Local.Min.X && L.X < Local.Max.X && L.Y > Local.Min.Y && L.Y < Local.Max.Y;
		L.X = FMath::Clamp(L.X, Local.Min.X, Local.Max.X);
		L.Y = FMath::Clamp(L.Y, Local.Min.Y, Local.Max.Y);
		L.Z = Local.Min.Z;
		if (!bInside && Target->ActorHasTag(TEXT("Mounded")))
		{
			// a mine set into a mountain or a hill (the maps tag every mine Mounded): its sides and back are under the
			// ground, so it is reached, worked on and struck at its front (local +Y), a step in from the corners
			L.Y = Local.Max.Y;
			L.X = FMath::Clamp(L.X, FMath::Min(Local.Min.X + 150.f, 0.f), FMath::Max(Local.Max.X - 150.f, 0.f));
		}
		const FVector W = T.TransformPosition(L);
		if (OutPoint)
		{
			*OutPoint = W;
		}
		return bInside ? 0.f : FVector::Dist2D(W, From);
	}
	if (OutPoint)
	{
		*OutPoint = Target->GetActorLocation();
	}
	return FVector::Dist2D(Target->GetActorLocation(), From);
}

namespace
{
	/** A building's hit box in its mesh component's space (see VLRules::BuildingHitPad). */
	bool HitBoxOf(const FVLBuildingState& B, FTransform& OutT, FBox& OutLocal, float Extra)
	{
		if (!BoxOf(B.Actor.Get(), OutT, OutLocal))
		{
			return false;
		}
		if (B.IsSite())
		{
			OutLocal.Max.Z = OutLocal.Min.Z + (OutLocal.Max.Z - OutLocal.Min.Z) * FMath::Clamp(B.Build, 0.2f, 1.f);
		}
		const FVector S = OutT.GetScale3D().GetAbs().ComponentMax(FVector(0.01f));
		const float Pad = VLRules::BuildingHitPad + Extra;
		OutLocal.Min.X -= Pad / S.X;
		OutLocal.Max.X += Pad / S.X;
		OutLocal.Min.Y -= Pad / S.Y;
		OutLocal.Max.Y += Pad / S.Y;
		OutLocal.Min.Z -= 30.f / S.Z;           // (an arrow in the ground at its foot)
		OutLocal.Max.Z += Pad / S.Z;
		return true;
	}

	/** Where along A..B (0..1) the stretch enters Box (0 if A is inside); false if it misses. */
	bool SegmentEntersBox(const FVector& A, const FVector& B, const FBox& Box, float& OutT)
	{
		float T0 = 0.f, T1 = 1.f;
		const FVector D = B - A;
		for (int32 k = 0; k < 3; ++k)
		{
			if (FMath::Abs(D[k]) < UE_KINDA_SMALL_NUMBER)
			{
				if (A[k] < Box.Min[k] || A[k] > Box.Max[k])
				{
					return false;
				}
				continue;
			}
			float Ta = (Box.Min[k] - A[k]) / D[k], Tb = (Box.Max[k] - A[k]) / D[k];
			if (Ta > Tb)
			{
				Swap(Ta, Tb);
			}
			T0 = FMath::Max(T0, Ta);
			T1 = FMath::Min(T1, Tb);
			if (T0 > T1)
			{
				return false;
			}
		}
		OutT = T0;
		return true;
	}
}

AActor* UVLBattle::BuildingOnPath(const FVector& From, const FVector& To, int32 Team, float& OutT) const
{
	AActor* Best = nullptr;
	float BestT = 2.f;
	const FBox Seg = FBox(From.ComponentMin(To), From.ComponentMax(To)).ExpandBy(VLRules::BuildingHitPad + 50.f);
	for (const FVLBuildingState& B : Buildings)
	{
		AActor* A = B.Actor.Get();
		if (!A || !B.IsAlive() || B.Team < 0 || B.Team == Team)
		{
			continue;
		}
		FVector Origin, Extent;
		A->GetActorBounds(false, Origin, Extent);
		if (!Seg.Intersect(FBox(Origin - Extent, Origin + Extent)))
		{
			continue;
		}
		FTransform T;
		FBox Local;
		float At = 0.f;
		if (HitBoxOf(B, T, Local, 0.f) && SegmentEntersBox(T.InverseTransformPosition(From), T.InverseTransformPosition(To), Local, At) && At < BestT)
		{
			BestT = At;
			Best = A;
		}
	}
	OutT = BestT;
	return Best;
}

AActor* UVLBattle::BuildingAt(const FVector& P, int32 Team, float Extra) const
{
	for (const FVLBuildingState& B : Buildings)
	{
		AActor* A = B.Actor.Get();
		FTransform T;
		FBox Local;
		if (A && B.IsAlive() && B.Team >= 0 && B.Team != Team && HitBoxOf(B, T, Local, Extra) && Local.IsInside(T.InverseTransformPosition(P)))
		{
			return A;
		}
	}
	return nullptr;
}

FVector UVLBattle::AimPoint(const AActor* Target, const FVector& From) const
{
	if (const AVLKing* U = Cast<AVLKing>(Target))
	{
		return U->GetActorLocation() + FVector(0.f, 0.f, 10.f);         // the chest
	}
	if (FindBuilding(Target))
	{
		FVector P;
		DistanceTo(Target, From, &P);
		FVector Origin, Extent;
		Target->GetActorBounds(true, Origin, Extent);
		// a little into the wall that faces the archer, at a man's height and a half
		const FVector In = (FVector(Origin.X, Origin.Y, P.Z) - P).GetSafeNormal2D();
		P += In * 60.f;
		P.Z = Origin.Z - Extent.Z + FMath::Min(260.f, Extent.Z);
		return P;
	}
	return Target ? Target->GetActorLocation() + FVector(0.f, 0.f, 95.f) : FVector::ZeroVector;
}

void UVLBattle::FrontOf(const AActor* Building, FVector& OutDoor, FVector& OutRally, FVector& OutFront) const
{
	// Buildings face their local +Y (Blender's -Y): the troop appears in front of the hall (in the yard, if it has one)
	FVector Origin, Extent;
	Building->GetActorBounds(true, Origin, Extent);
	OutFront = Building->GetActorRotation().RotateVector(FVector(0.f, 1.f, 0.f));
	const float Reach = FMath::Abs(OutFront.X) * Extent.X + FMath::Abs(OutFront.Y) * Extent.Y;
	const FVector Base(Origin.X, Origin.Y, Building->GetActorLocation().Z);
	OutDoor = Base + OutFront * FMath::Min(Reach * 0.3f, 250.f);
	OutRally = Base + OutFront * (Reach + 520.f);
	if (UVLGrid* Grid = UVLGrid::Get(Building); Grid && Grid->EnsureBuilt())
	{
		const int32 In = Grid->NearestNode(OutDoor, 40, Grid->MainRegion());
		if (In != INDEX_NONE)
		{
			OutDoor = Grid->NodePos(In);
		}
		const int32 Out = Grid->NearestNode(OutRally, 40, Grid->MainRegion());
		if (Out != INDEX_NONE)
		{
			OutRally = Grid->NodePos(Out);
		}
	}
}

// ------------------------------------------------------------------------------------------------ damage

float UVLBattle::Damage(AActor* Target, float Amount, AActor* By, int32 ByTeam)
{
	UWorld* World = GetWorld();
	const int32 TargetTeam = TeamOf(Target);
	if (!World || !Target || Amount <= 0.f || TargetTeam == Neutral || TargetTeam == ByTeam || !IsAlive(Target))
	{
		return 0.f;
	}
	const double Now = World->GetTimeSeconds();
	AVLKing* Striker = Cast<AVLKing>(By);
	if (AVLKing* U = Cast<AVLKing>(Target))
	{
		U->LastStruckBy = By;
		U->LastStruckTime = Now;
		U->LastHurtTime = Now;
		if (BattleLog())
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("hit: %s takes %.0f from %s (%.0f left)"), *U->GetDisplayName(), Amount, By ? *By->GetName() : TEXT("-"), U->GetHealth() - Amount);
		}
		// friends close by come to its help (those not busy and free to fight; a defensive one lets go at its leash)
		if (Striker && IsAlive(Striker))
		{
			FVLUnits Near;
			UnitsNear(U->GetActorLocation(), VLRules::HelpRadius, Near);
			for (AVLKing* F : Near)
			{
				if (F == U || !F->IsAlive() || F->Team != U->Team || FVector::DistSquared2D(F->GetActorLocation(), U->GetActorLocation()) >= FMath::Square(VLRules::HelpRadius))
				{
					continue;
				}
				bool bBusy = false;
				CombatTarget(F, &bBusy);
				if (!bBusy && !InPlayersHands(F) && (!F->HasOrder() || F->bAttackMove) && !F->IsHolding() && UVLCommand::CanAttack(F))
				{
					Engage(F, Striker);
				}
			}
		}
		// the player's troops hit away from where the player is looking: an alert (at most every 15 s)
		if (U->Team == Player && State == EVLMatch::Playing && Now - LastTroopAlert > 15.0)
		{
			const APlayerController* PC = World->GetFirstPlayerController();
			const AVLKing* Me = PC ? Cast<AVLKing>(PC->GetPawn()) : nullptr;
			if (Me && FVector::Dist2D(Me->GetListenFocus(), U->GetActorLocation()) > 3000.f)
			{
				LastTroopAlert = Now;
				const FVector At = U->GetActorLocation();
				PushAlert(TEXT("Your troops are under attack!"), EVLAlert::Attack, &At);
				Play2D(TEXT("S_AttackAlert"), 0.5f);
			}
		}
		if (UVLCommand* Command = UVLCommand::Get(this); Command && By && IsAlive(By))
		{
			// a Builder or the king under guard calls its guards in (a guard struck: the other guards of its ward); a
			// roaming Spy runs home
			TArray<AVLKing*> Guards;
			Command->GetGuards(U, Guards);
			if (AActor* Ward = Command->GuardWardOf(U))
			{
				TArray<AVLKing*> Fellows;
				Command->GetGuards(Ward, Fellows);
				Guards.Append(Fellows);
			}
			for (AVLKing* F : Guards)
			{
				bool bBusy = false;
				CombatTarget(F, &bBusy);
				if (!bBusy && !InPlayersHands(F) && UVLCommand::CanAttack(F))
				{
					Engage(F, By);
				}
			}
			Command->OnStruck(U, By);
		}
		if (ByTeam == 0 || ByTeam == 1)
		{
			Kingdoms[ByTeam].DamageBy[StrikerClass(By)] += FMath::Min(Amount, U->GetHealth());
		}
		U->ReceiveDamage(Amount, By);       // (at 0 it calls OnUnitKilled)
		return Amount;
	}
	FVLBuildingState* B = FindBuilding(Target);
	if (!B)
	{
		return 0.f;
	}
	if (Striker)
	{
		Amount *= Striker->KindRules().BuildingScale;     // arrows barely scratch stone
	}
	else
	{
		Amount *= VLRules::Troop(EVLUnitKind::Archer).BuildingScale;         // a tower's arrows
	}
	if (ByTeam == 0 || ByTeam == 1)
	{
		Kingdoms[ByTeam].BuildingDamageBy[StrikerClass(By)] += FMath::Min(Amount, B->Health);
	}
	B->Health = FMath::Max(0.f, B->Health - Amount);
	B->LastHit = Now;
	FVector Wall = Target->GetActorLocation();
	if (By)
	{
		DistanceTo(Target, By->GetActorLocation(), &Wall);
		Wall.Z += 120.f;
	}
	PlayAt(TEXT("S_BuildingHit"), Wall, 0.45f, 4000.f, 0.25f);
	if (BattleLog())
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("hit: %s of team %d takes %.0f from %s (%.0f of %.0f left)"), *B->Name, B->Team, Amount, By ? *By->GetName() : TEXT("-"), B->Health, B->MaxHealth);
	}
	if (B->Team == Player && State == EVLMatch::Playing && Now - B->LastAlert > 10.0)
	{
		B->LastAlert = Now;
		const FVector At = Target->GetActorLocation();
		PushAlert(FString::Printf(TEXT("Your %s is under attack!"), *B->Name), EVLAlert::Attack, &At);
		Play2D(TEXT("S_AttackAlert"), 0.55f);
	}
	// troops of its side nearby come to its defence (and its guards, wherever they stand)
	if (Striker && Striker->IsAlive())
	{
		if (UVLCommand* Command = UVLCommand::Get(this))
		{
			TArray<AVLKing*> Guards;
			Command->GetGuards(Target, Guards);
			for (AVLKing* F : Guards)
			{
				bool bBusy = false;
				CombatTarget(F, &bBusy);
				if (!bBusy && !InPlayersHands(F) && UVLCommand::CanAttack(F))
				{
					Engage(F, Striker);
				}
			}
		}
		FVLUnits Friends;
		GetAllUnits(Friends);
		const int32 BuildingTeam = B->Team;         // (an order may register a building: B is not kept over the loop)
		for (AVLKing* F : Friends)
		{
			if (!F->IsAlive() || F->Team != BuildingTeam)
			{
				continue;
			}
			bool bBusy = false;
			CombatTarget(F, &bBusy);
			if (!bBusy && !InPlayersHands(F) && (!F->HasOrder() || F->bAttackMove) && !F->IsHolding() && UVLCommand::CanAttack(F)
				&& DistanceTo(Target, F->GetFeet()) < 1300.f)
			{
				Engage(F, Striker);
			}
		}
	}
	if (B->Health <= 0.f)
	{
		Collapse(*B, By, ByTeam);
	}
	return Amount;
}

void UVLBattle::OnUnitKilled(AVLKing* Unit, AActor* By)
{
	if (!Unit || Unit->IsDead())
	{
		return;
	}
	const int32 ByTeam = TeamOf(By);
	if (Unit->IsTroop() && !Unit->bTowerGuard && (Unit->Team == 0 || Unit->Team == 1))
	{
		++Kingdoms[Unit->Team].Lost;
		++Kingdoms[Unit->Team].LostKind[FMath::Min(int32(Unit->KindId()), 5)];
	}
	if (ByTeam == 0 || ByTeam == 1)
	{
		++Kingdoms[ByTeam].Killed;
		++Kingdoms[ByTeam].KillsBy[StrikerClass(By)];
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("%s (team %d) falls to %s"), *Unit->GetDisplayName(), Unit->Team, By ? *By->GetName() : TEXT("-"));
	PlayAt(TEXT("S_Death"), Unit->GetActorLocation(), 0.5f, 4500.f, 0.15f);
	if (UVLCommand* Command = UVLCommand::Get(this))
	{
		Command->OnUnitDied(Unit);
	}
	Unit->Die();
	if (!Unit->IsTroop() && Unit->Team == Player)
	{
		const FVector At = Unit->GetActorLocation();
		PushAlert(FString::Printf(TEXT("King David has fallen! He will rise again at the castle in %.0f s"), VLRules::KingRespawnSeconds), EVLAlert::Lost, &At);
		Play2D(TEXT("S_AttackAlert"), 0.6f);
	}
}

void UVLBattle::Collapse(FVLBuildingState& B, AActor* By, int32 ByTeam, bool bDemolished)
{
	if (B.bDestroyed)
	{
		return;
	}
	AActor* A = B.Actor.Get();
	B.bDestroyed = true;
	B.Collapse = 0.f;
	if (B.Kind == EVLBuilding::Mine)
	{
		// a mine is part of its map (set into a mountain or a hill): it does not slump into the ground. It stands
		// abandoned, nobody's, and can be claimed again (UVLConstruction::ClaimMine)
		B.Collapse = -1.f;
	}
	B.Health = 0.f;
	B.Queue.Reset();        // (recruits waiting there are lost with it)
	B.UpgradeLeft = -1.f;
	if (!bDemolished)
	{
		++Kingdoms[FMath::Clamp(B.Team, 0, 1)].BuildingsLost;
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("%s of team %d %s by %s"), *B.Name, B.Team, bDemolished ? TEXT("demolished") : TEXT("destroyed"), By ? *By->GetName() : TEXT("-"));
	if (A)
	{
		PlayAt(TEXT("S_BuildingCollapse"), A->GetActorLocation(), 0.8f, 9000.f, 0.3f);
		const FVector At = A->GetActorLocation();
		if (bDemolished)
		{
			// (pulled down by its own side: UVLConstruction::Demolish says what came back)
		}
		else if (B.Team == Player)
		{
			PushAlert(FString::Printf(TEXT("Your %s has been destroyed"), *B.Name), EVLAlert::Lost, &At);
		}
		else
		{
			PushAlert(FString::Printf(TEXT("The enemy's %s is destroyed"), *B.Name), EVLAlert::Good, &At);
		}
		DismissTowerGuards(B);                  // the tower's own archers go with it
		if (UVLCommand* Command = UVLCommand::Get(this))
		{
			if (UVLCommand::IsTower(A))
			{
				Command->EmptyTower(A);         // whoever stood on the lookout comes down
			}
		}
	}
	// a fallen storehouse takes its stock with it: what the kingdom can no longer hold is lost
	const int32 T = FMath::Clamp(B.Team, 0, 1);
	Kingdoms[T].Gold = FMath::Min(Kingdoms[T].Gold, GetStorage(T, EVLRes::Gold));
	Kingdoms[T].Food = FMath::Min(Kingdoms[T].Food, GetStorage(T, EVLRes::Food));
	CheckEnd();
}

void UVLBattle::TickCollapse(float Dt)
{
	for (FVLBuildingState& B : Buildings)
	{
		AActor* A = B.Actor.Get();
		if (!A || B.Collapse < 0.f)
		{
			continue;
		}
		// it slumps into the ground with a shudder, and is gone
		B.Collapse += Dt;
		FVector Origin, Extent;
		A->GetActorBounds(true, Origin, Extent);
		const float T = FMath::Clamp(B.Collapse / 2.6f, 0.f, 1.f);
		const float Sink = (B.Rest.Z - (Origin.Z - Extent.Z)) + Extent.Z * 2.f;
		const FVector Shake(FMath::Sin(B.Collapse * 47.f) * 8.f * (1.f - T), FMath::Cos(B.Collapse * 39.f) * 8.f * (1.f - T), 0.f);
		A->SetActorLocation(B.Rest + Shake - FVector(0.f, 0.f, FMath::Max(Sink, 300.f) * T * T), false, nullptr, ETeleportType::TeleportPhysics);
		if (T >= 1.f)
		{
			B.Collapse = -1.f;
			A->SetActorHiddenInGame(true);
			A->SetActorEnableCollision(false);
			// where it stood can be walked again: the path grid is sampled again there (UVLGrid::RebuildArea; a
			// whole Build took 1.5 s on the realm)
			if (UVLGrid* Grid = UVLGrid::Get(this))
			{
				Grid->RebuildArea(FBox2D(FVector2D(Origin - Extent) - FVector2D(300.f, 300.f), FVector2D(Origin + Extent) + FVector2D(300.f, 300.f)));
			}
		}
	}
	if (bRegrid)
	{
		bRegrid = false;
		if (UVLGrid* Grid = UVLGrid::Get(this))
		{
			Grid->Build();
		}
	}
}

// ------------------------------------------------------------------------------------------------ economy

int32 UVLBattle::GetStock(int32 Team, EVLRes Res) const
{
	const FVLKingdom& K = GetKingdom(Team);
	return Res == EVLRes::Gold ? K.Gold : K.Food;
}

int32 UVLBattle::GetCastleLevel(int32 Team) const
{
	const AActor* C = GetCastle(Team);
	const FVLBuildingState* B = FindBuilding(C);
	return B ? B->Level : 1;
}

int32 UVLBattle::GetStorage(int32 Team, EVLRes Res) const
{
	int32 Cap = VLRules::Level(EVLBuilding::Castle, GetCastleLevel(Team)).Storage;
	const EVLBuilding Store = Res == EVLRes::Gold ? EVLBuilding::Treasury : EVLBuilding::Granary;
	for (const FVLBuildingState& B : Buildings)
	{
		if (B.Kind == Store && B.Team == Team && B.IsAlive() && !B.IsSite())
		{
			Cap += VLRules::Level(Store, B.Level).Storage;
		}
	}
	return Cap;
}

void UVLBattle::AddStock(int32 Team, EVLRes Res, int32 Amount, bool bIgnoreStorage)
{
	if (Team != 0 && Team != 1)
	{
		return;
	}
	FVLKingdom& K = Kingdoms[Team];
	int32& V = Res == EVLRes::Gold ? K.Gold : K.Food;
	const int32 Cap = GetStorage(Team, Res);
	if (Amount > 0 && !bIgnoreStorage)
	{
		V = FMath::Max(V, FMath::Min(V + Amount, Cap));     // income beyond the stores is lost
	}
	else
	{
		V = FMath::Max(0, V + Amount);
	}
	if (Amount > 0)
	{
		K.Pulse[int32(Res)] = 1.f;
	}
}

bool UVLBattle::CanAfford(int32 Team, const FVLCost& Cost) const
{
	const FVLKingdom& K = GetKingdom(Team);
	return K.Gold >= Cost.Gold && K.Food >= Cost.Food;
}

bool UVLBattle::TrySpend(int32 Team, const FVLCost& Cost, bool bQuiet)
{
	if (Team != 0 && Team != 1)
	{
		return false;
	}
	FVLKingdom& K = Kingdoms[Team];
	if (!CanAfford(Team, Cost))
	{
		if (Team == Player && !bQuiet)
		{
			if (K.Gold < Cost.Gold)
			{
				K.Flash[0] = 1.f;
			}
			if (K.Food < Cost.Food)
			{
				K.Flash[1] = 1.f;
			}
			PushAlert(K.Food < Cost.Food ? FString::Printf(TEXT("Not enough food (%d needed)"), Cost.Food) : FString::Printf(TEXT("Not enough gold (%d needed)"), Cost.Gold));
			Play2D(TEXT("S_UIError"), 0.5f);
		}
		return false;
	}
	K.Gold -= Cost.Gold;
	K.Food -= Cost.Food;
	K.Spent[0] += Cost.Gold;
	K.Spent[1] += Cost.Food;
	return true;
}

int32 UVLBattle::GetPopulation(int32 Team) const
{
	int32 N = 0;
	for (const AVLKing* U : AllUnits())
	{
		N += (U->IsAlive() && U->Team == Team && !U->bTowerGuard) ? U->KindRules().Pop : 0;     // (a tower's own archers are free)
	}
	return N;
}

int32 UVLBattle::GetQueuedPopulation(int32 Team) const
{
	int32 N = 0;
	for (const FVLBuildingState& B : Buildings)
	{
		if (B.Team == Team && B.IsAlive())
		{
			for (const FString& K : B.Queue)
			{
				N += VLRules::Troop(K).Pop;
			}
		}
	}
	return N;
}

int32 UVLBattle::GetPopulationCeiling(int32 Team) const
{
	return VLRules::Level(EVLBuilding::Castle, GetCastleLevel(Team)).Ceiling;
}

int32 UVLBattle::GetPopulationCap(int32 Team) const
{
	int32 Housing = 0;
	for (const FVLBuildingState& B : Buildings)
	{
		if (B.Team == Team && B.IsAlive() && !B.IsSite() && (B.Kind == EVLBuilding::Castle || B.Kind == EVLBuilding::Farm))      // (a site houses nobody yet)
		{
			Housing += VLRules::Level(B.Kind, B.Level).Housing;
		}
	}
	return FMath::Min(Housing, GetPopulationCeiling(Team));
}

float UVLBattle::IncomeScale(int32 Team) const
{
	const FVLCommander* C = (Team == 0 || Team == 1) ? Commanders[Team].Get() : nullptr;
	return (C && C->bActive) ? C->Prof.IncomeScale : 1.f;
}

float UVLBattle::GetIncomePerMinute(int32 Team, EVLRes Res) const
{
	const EVLBuilding Kind = Res == EVLRes::Gold ? EVLBuilding::Mine : EVLBuilding::Farm;
	float Sum = 0.f;
	for (const FVLBuildingState& B : Buildings)
	{
		if (B.Kind == Kind && B.Team == Team && B.IsAlive() && !B.IsSite())
		{
			Sum += FMath::RoundToFloat(VLRules::Level(Kind, B.Level).Yield * IncomeScale(Team));
		}
	}
	return Sum * 60.f / VLRules::PayoutInterval;
}

void UVLBattle::TickKingRest(float Dt)
{
	const UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	const double Now = World->GetTimeSeconds();
	for (AVLKing* U : AllUnits())
	{
		if (IsValid(U) && U->KindId() == EVLUnitKind::King && U->IsAlive() && U->GetHealthFrac() < 1.f && Now - U->LastHurtTime >= VLRules::KingRestDelay)
		{
			U->Heal(U->MaxHealth * VLRules::KingRestRate * Dt);
		}
	}
}

void UVLBattle::TickEconomy(float Dt)
{
	for (int32 t = 0; t < 2; ++t)
	{
		for (int32 r = 0; r < 2; ++r)
		{
			Kingdoms[t].Flash[r] = FMath::Max(0.f, Kingdoms[t].Flash[r] - Dt / 0.55f);
			Kingdoms[t].Pulse[r] = FMath::Max(0.f, Kingdoms[t].Pulse[r] - Dt / 0.6f);
		}
	}
	const UWorld* World = GetWorld();
	for (FVLBuildingState& B : Buildings)
	{
		AActor* A = B.Actor.Get();
		if (!B.IsWorking() || (B.Kind != EVLBuilding::Farm && B.Kind != EVLBuilding::Mine))
		{
			continue;           // (a site, or one under repair, pays nothing)
		}
		B.Payout += Dt;
		if (B.Payout < VLRules::PayoutInterval)
		{
			continue;
		}
		// the harvest / the ore comes in: no workers here, it simply arrives (FarmPayoutInterval, MinePayoutInterval)
		B.Payout -= VLRules::PayoutInterval;
		const bool bGold = B.Kind == EVLBuilding::Mine;
		const int32 Amount = FMath::RoundToInt(VLRules::Level(B.Kind, B.Level).Yield * IncomeScale(B.Team));
		if (B.Team == 0 || B.Team == 1)
		{
			FVLKingdom& K = Kingdoms[B.Team];
			const int32 Was = bGold ? K.Gold : K.Food;
			AddStock(B.Team, bGold ? EVLRes::Gold : EVLRes::Food, Amount);
			K.Earned[bGold ? 0 : 1] += Amount;
			K.Wasted[bGold ? 0 : 1] += Amount - ((bGold ? K.Gold : K.Food) - Was);       // (beyond the stores: lost)
		}
		if (B.Team == Player && Amount > 0)
		{
			FVector Origin, Extent;
			A->GetActorBounds(true, Origin, Extent);
			FVLPopup& P = Popups.AddDefaulted_GetRef();
			P.At = Origin + FVector(0.f, 0.f, Extent.Z * 0.8f);
			P.Text = FString::Printf(TEXT("+%d %s"), Amount, bGold ? TEXT("gold") : TEXT("food"));
			P.Amount = Amount;
			P.bGold = bGold;
			P.Colour = bGold ? FLinearColor(1.f, 0.82f, 0.25f) : FLinearColor(0.85f, 0.95f, 0.45f);
			P.Time = World->GetRealTimeSeconds();
			PlayAt(bGold ? TEXT("S_CoinPayout") : TEXT("S_GrainPayout"), Origin, 0.22f, 3500.f, 0.5f);
		}
	}
	const double Now = World->GetRealTimeSeconds();
	Popups.RemoveAll([Now](const FVLPopup& P) { return Now - P.Time > 1.5; });
}

// ------------------------------------------------------------------------------------------------ training

FString UVLBattle::TroopFor(const AActor* Building)
{
	if (!Building)
	{
		return FString();
	}
	const EVLBuilding Kind = VLRules::KindFromName(TagValue(Building, TEXT("Name:")));
	return Kind == EVLBuilding::Barracks ? TEXT("Swordsman") : (Kind == EVLBuilding::Range ? TEXT("Archer") : (Kind == EVLBuilding::Castle ? TEXT("Spy") : FString()));
}

bool UVLBattle::TrainsKind(const AActor* Building, const FString& Kind)
{
	// each its own troop; the castle the Spy and, as in the main game, the Builders
	return !Kind.IsEmpty() && (Kind == TroopFor(Building) || (Kind == TEXT("Builder") && VLRules::KindFromName(TagValue(Building, TEXT("Name:"))) == EVLBuilding::Castle));
}

int32 UVLBattle::GetSpyCount(int32 Team, int32* OutQueued) const
{
	int32 Alive = 0, Queued = 0;
	for (const AVLKing* U : AllUnits())
	{
		Alive += (U->IsAlive() && U->Team == Team && U->KindId() == EVLUnitKind::Spy) ? 1 : 0;
	}
	for (const FVLBuildingState& B : Buildings)
	{
		if (B.Team == Team && B.IsAlive())
		{
			for (const FString& K : B.Queue)
			{
				Queued += K == TEXT("Spy") ? 1 : 0;
			}
		}
	}
	if (OutQueued)
	{
		*OutQueued = Queued;
	}
	return Alive;
}

FString UVLBattle::SpyRefusal(int32 Team) const
{
	if (GetCastleLevel(Team) < VLRules::SpyCastleLevel)
	{
		return FString::Printf(TEXT("A Spy needs the castle at level %d"), VLRules::SpyCastleLevel);
	}
	int32 Queued = 0;
	if (GetSpyCount(Team, &Queued) + Queued >= VLRules::MaxSpies)
	{
		return TEXT("You already have a Spy (a kingdom has only one at a time)");
	}
	if (const float Left = GetSpyCooldown(Team); Left > 0.f)
	{
		return FString::Printf(TEXT("The next Spy can be trained in %s"), *ClockText(Left));
	}
	return FString();
}

bool UVLBattle::IsNoticed(const AVLKing* Unit, float Distance, float Range)
{
	return Unit && Distance <= Range * Unit->KindRules().Notice;
}

FString UVLBattle::TrainRefusal(const AActor* Building, const FString& InKind) const
{
	const FVLBuildingState* B = FindBuilding(Building);
	const FString Kind = InKind.IsEmpty() ? TroopFor(Building) : InKind;
	if (!B || Kind.IsEmpty() || !B->IsAlive() || !TrainsKind(Building, Kind))
	{
		return TEXT("It trains nobody");
	}
	if (B->IsSite())
	{
		return FString::Printf(TEXT("The %s is still being built"), *B->Name);
	}
	const VLRules::FTroop& T = VLRules::Troop(Kind);
	if (Kind == TEXT("Builder"))
	{
		// no housing, but a limit of their own: the castle's level (alive and in training)
		int32 Have = 0;
		for (const AVLKing* U : AllUnits())
		{
			Have += (U->IsAlive() && U->Team == B->Team && U->KindId() == EVLUnitKind::Builder) ? 1 : 0;
		}
		for (const FVLBuildingState& S : Buildings)
		{
			if (S.Team == B->Team && S.IsAlive())
			{
				Have += S.Queue.FilterByPredicate([](const FString& K) { return K == TEXT("Builder"); }).Num();
			}
		}
		const int32 Max = VLBuild::MaxBuilders(GetCastleLevel(B->Team));
		if (Have >= Max)
		{
			return FString::Printf(TEXT("Builders %d/%d: raise the castle a level for more"), Have, Max);
		}
	}
	if (Kind == TEXT("Spy"))
	{
		// castle level, one at a time, and a wait between two
		if (const FString Why = SpyRefusal(B->Team); !Why.IsEmpty())
		{
			return Why;
		}
	}
	if (T.Pop > 0 && GetPopulation(B->Team) + GetQueuedPopulation(B->Team) + T.Pop > GetPopulationCap(B->Team))
	{
		return GetPopulationCap(B->Team) >= GetPopulationCeiling(B->Team) ? TEXT("Housing full: raise the castle a level for more troops")
			: TEXT("Housing full: raise the castle or a farm a level to house more troops");
	}
	if (!CanAfford(B->Team, T.Cost))
	{
		return GetStock(B->Team, EVLRes::Food) < T.Cost.Food ? FString::Printf(TEXT("Not enough food (%d needed)"), T.Cost.Food)
			: FString::Printf(TEXT("Not enough gold (%d needed)"), T.Cost.Gold);
	}
	return FString();
}

int32 UVLBattle::Train(AActor* Building, int32 Count, bool bQuiet, const FString& InKind)
{
	FVLBuildingState* B = FindBuilding(Building);
	const FString Kind = InKind.IsEmpty() ? TroopFor(Building) : InKind;
	if (!B || Kind.IsEmpty() || !B->IsAlive() || !TrainsKind(Building, Kind))
	{
		return 0;
	}
	int32 Queued = 0;
	for (int32 i = 0; i < Count; ++i)
	{
		// each recruit is paid for and housed when it is queued (a batch takes as many as can be): no queue limit
		const FString Why = TrainRefusal(Building, Kind);
		if (!Why.IsEmpty())
		{
			if (B->Team == Player && !bQuiet && Queued == 0)
			{
				const bool bFood = Why.StartsWith(TEXT("Not enough"));
				if (bFood)
				{
					TrySpend(B->Team, VLRules::Troop(Kind).Cost);   // (fails: flashes the counter that fell short and says so)
				}
				if (!bFood)
				{
					PushAlert(Why);
					Play2D(TEXT("S_UIError"), 0.5f);
				}
			}
			break;
		}
		TrySpend(B->Team, VLRules::Troop(Kind).Cost, true);
		if (B->Queue.Num() == 0)
		{
			B->TrainClock = 0.f;
		}
		B->Queue.Add(Kind);
		++Queued;
		if (Kind == TEXT("Spy"))
		{
			SetSpyCooldown(B->Team, VLRules::SpyCooldown);      // the wait before the next runs from now: queued and paid for
			break;                                              // (a kingdom has one: no batch)
		}
	}
	if (Queued > 0)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("train: %d %s at %s (team %d), queue %d, left %d gold %d food"), Queued, *Kind, *B->Name, B->Team, B->Queue.Num(), GetStock(B->Team, EVLRes::Gold),
			GetStock(B->Team, EVLRes::Food));
	}
	return Queued;
}

int32 UVLBattle::QueueLength(const AActor* Building) const
{
	const FVLBuildingState* B = FindBuilding(Building);
	return B ? B->Queue.Num() : 0;
}

float UVLBattle::TrainSeconds(const AActor* Building, const FString& InKind) const
{
	const FVLBuildingState* B = FindBuilding(Building);
	const FString Kind = InKind.IsEmpty() ? TroopFor(Building) : InKind;
	if (!B || Kind.IsEmpty())
	{
		return 0.f;
	}
	return VLRules::Troop(Kind).TrainSeconds / FMath::Max(VLRules::Level(B->Kind, B->Level).TrainSpeed, 0.1f);
}

float UVLBattle::TrainProgress(const AActor* Building) const
{
	const FVLBuildingState* B = FindBuilding(Building);
	return (B && B->Queue.Num() > 0) ? FMath::Clamp(B->TrainClock / FMath::Max(TrainSeconds(Building, B->Queue[0]), 0.1f), 0.f, 1.f) : 0.f;
}

void UVLBattle::SetRally(AActor* Building, const FVector& Ground, bool bClear)
{
	if (FVLBuildingState* B = FindBuilding(Building))
	{
		B->bHasRally = !bClear;
		B->Rally = Ground;
	}
}

void UVLBattle::SetFeedPlatoon(AActor* Building, int32 Platoon)
{
	if (FVLBuildingState* B = FindBuilding(Building))
	{
		B->FeedPlatoon = Platoon;
	}
}

void UVLBattle::TickTraining(float Dt)
{
	for (float& Left : SpyCooldownLeft)
	{
		Left = FMath::Max(0.f, Left - Dt);
	}
	for (FVLBuildingState& B : Buildings)
	{
		if (!B.IsWorking() || B.Queue.Num() == 0)
		{
			continue;           // (under repair it trains nothing: out of action)
		}
		// (it keeps training while it is raised a level)
		B.TrainClock += Dt;
		if (B.TrainClock >= TrainSeconds(B.Actor.Get(), B.Queue[0]))
		{
			B.TrainClock = 0.f;
			const FString Kind = B.Queue[0];
			B.Queue.RemoveAt(0);
			SpawnRecruit(B, Kind);
		}
	}
}

AVLTroop* UVLBattle::SpawnTroop(const FString& Kind, int32 Team, const FVector& Ground, float Yaw)
{
	UWorld* World = GetWorld();
	const TSoftObjectPtr<UVLCharacterData> Data = AVLTroop::DataFor(Kind);
	if (!World || !Data.LoadSynchronous())
	{
		UE_LOG(LogSovereignRealms, Warning, TEXT("no character data for %s (%s)"), *Kind, *Data.ToString());
		return nullptr;
	}
	const FTransform At(FRotator(0.f, Yaw, 0.f), Ground + FVector(0.f, 0.f, 95.f));
	AVLTroop* T = World->SpawnActorDeferred<AVLTroop>(AVLTroop::StaticClass(), At, nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn);
	if (!T)
	{
		return nullptr;
	}
	const FString Prefix = Team == Enemy ? TEXT("Enemy ") : TEXT("");
	const int32 Number = ++Numbers.FindOrAdd(Prefix + Kind);
	T->SetCharacterData(Data);
	T->SetKind(Kind);
	T->Team = Team;
	T->SetDisplayName(FString::Printf(TEXT("%s%s %d"), *Prefix, *Kind, Number));
	T->FinishSpawning(At);
	T->RefreshSilhouette();         // (its side's stencil and cloth: the enemy's troops are red and do not show through walls)
	return T;
}

void UVLBattle::SpawnRecruit(FVLBuildingState& B, const FString& Kind)
{
	AActor* A = B.Actor.Get();
	if (!A)
	{
		return;
	}
	// the troop appears in front of the hall and walks out to its rally point, gathering there in rows of five
	FVector Door, Rally, Front;
	FrontOf(A, Door, Rally, Front);
	const FVector Side(-Front.Y, Front.X, 0.f);
	const int32 N = B.Trained++;
	AVLTroop* T = SpawnTroop(Kind, B.Team, Door, Front.Rotation().Yaw);
	if (!T)
	{
		return;
	}
	++Kingdoms[FMath::Clamp(B.Team, 0, 1)].Recruited;
	++Kingdoms[FMath::Clamp(B.Team, 0, 1)].RecruitedKind[FMath::Min(int32(T->KindId()), 5)];
	UVLCommand* Command = UVLCommand::Get(this);
	FVector Goal = B.bHasRally ? B.Rally : Rally;
	bool bToPlatoon = false;
	// Where it goes, first that applies: the platoon this building feeds (its Joins chips); the recruits' platoon (the
	// platoon panel's flag), unless that one is full; the building's rally point; else its yard.
	// (the Spy goes alone; Builders join no platoon)
	int32 Join = INDEX_NONE;
	bool bFlagged = false;
	if (Command && B.Team == Player && Kind != TEXT("Spy") && Kind != TEXT("Builder"))
	{
		Join = B.FeedPlatoon;
		if (Join == INDEX_NONE)
		{
			Join = Command->RallyPlatoonFor();
			bFlagged = Join != INDEX_NONE;
		}
	}
	if (Join != INDEX_NONE)
	{
		// it joins the platoon, and marches to it (a wiped-out platoon a building feeds is formed again by it): it
		// falls in behind the platoon's leader and keeps with it (UVLCommand::OrderFollow), or, with no leader, walks
		// to where the platoon stands
		TArray<AVLKing*> Members;
		Command->GetPlatoon(Join, Members);
		AVLKing* Leader = Command->GetPlatoonLeader(Join);
		if (Members.Num() > 0)
		{
			Goal = Command->PlatoonCentre(Join);
			bToPlatoon = true;
		}
		Command->AddToPlatoon(Join, { T });
		if (bToPlatoon && Leader && Leader != T && Command->OrderFollow({ T }, Leader, false) > 0)
		{
			if (B.Team == Player)
			{
				Play2D(TEXT("S_RecruitReady"), 0.45f);
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("trained %s at %s (team %d): joins platoon %d%s, follows %s"), *T->GetDisplayName(), *B.Name, B.Team, Join + 1,
				bFlagged ? TEXT(" (the recruits' flag)") : TEXT(""), *Leader->GetDisplayName());
			return;
		}
	}
	// no rally point set and no platoon to march to: it waits in the building's yard (the barracks' fenced yard, the
	// range's), in ranks with those trained before it (UVLConstruction::SendToYard); a full yard sends it out as before
	UVLConstruction* Construction = UVLConstruction::Get(this);
	if (!B.bHasRally && !bToPlatoon && Construction && Construction->SendToYard(B, T))
	{
		if (B.Team == Player)
		{
			Play2D(TEXT("S_RecruitReady"), 0.45f);
		}
		UE_LOG(LogSovereignRealms, Log, TEXT("trained %s at %s (team %d): waits in the yard"), *T->GetDisplayName(), *B.Name, B.Team);
		return;
	}
	const FVector Slot = Goal + Front * ((N / 5 % 3) * 130.f) + Side * (((N % 5) - 2) * 125.f);
	FVector Fitted = Slot;
	if (UVLGrid* Grid = UVLGrid::Get(this); Grid && Grid->EnsureBuilt())
	{
		TArray<FVector> Out;
		const int32 Node = Grid->NearestNode(Goal, 40);
		Grid->FitSlots(Node != INDEX_NONE ? Grid->NodePos(Node) : Goal, { FVector2D(Slot) }, Out);
		if (Out.Num() > 0)
		{
			Fitted = Out[0];
		}
	}
	if (Command)
	{
		Command->OrderMove({ T }, Fitted, false, EVLFormation::Line);
	}
	if (B.Team == Player)
	{
		Play2D(TEXT("S_RecruitReady"), 0.45f);
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("trained %s at %s (team %d)"), *T->GetDisplayName(), *B.Name, B.Team);
}

// ------------------------------------------------------------------------------------------------ upgrades

FString UVLBattle::UpgradeRefusal(const AActor* Building, FVLCost* OutCost) const
{
	const FVLBuildingState* B = FindBuilding(Building);
	if (!B || !B->IsAlive())
	{
		return TEXT("-");
	}
	if (B->Level >= VLRules::NumLevels(B->Kind))
	{
		return B->Kind == EVLBuilding::Hall ? TEXT("-") : TEXT("At its top level");
	}
	if (B->IsSite())
	{
		return TEXT("Still being built");
	}
	if (B->UpgradeLeft >= 0.f)
	{
		return TEXT("Being raised");
	}
	const VLRules::FLevel& Next = VLRules::Level(B->Kind, B->Level + 1);
	if (OutCost)
	{
		*OutCost = Next.Cost;
	}
	if (Next.CastleLevel > GetCastleLevel(B->Team))
	{
		return FString::Printf(TEXT("Needs the castle at level %d"), Next.CastleLevel);
	}
	if (!CanAfford(B->Team, Next.Cost))
	{
		return GetStock(B->Team, EVLRes::Gold) < Next.Cost.Gold ? TEXT("Not enough gold") : TEXT("Not enough food");
	}
	return FString();
}

bool UVLBattle::Upgrade(AActor* Building, bool bQuiet)
{
	FVLBuildingState* B = FindBuilding(Building);
	FVLCost Cost;
	const FString Why = UpgradeRefusal(Building, &Cost);
	if (!B || !Why.IsEmpty())
	{
		if (B && B->Team == Player && !bQuiet && Why != TEXT("-"))
		{
			if (Why.StartsWith(TEXT("Not enough")))
			{
				TrySpend(B->Team, Cost);    // (flashes the counter, says so)
			}
			else
			{
				PushAlert(Why);
				Play2D(TEXT("S_UIError"), 0.5f);
			}
		}
		return false;
	}
	TrySpend(B->Team, Cost, true);
	B->UpgradeTotal = FMath::Max(VLRules::Level(B->Kind, B->Level + 1).Seconds, 1.f);
	B->UpgradeLeft = B->UpgradeTotal;
	UE_LOG(LogSovereignRealms, Log, TEXT("upgrade: %s of team %d to level %d (%d gold %d food, %.0f s)"), *B->Name, B->Team, B->Level + 1, Cost.Gold, Cost.Food, B->UpgradeTotal);
	return true;
}

void UVLBattle::TickUpgrades(float Dt)
{
	for (FVLBuildingState& B : Buildings)
	{
		if (!B.IsAlive() || B.UpgradeLeft < 0.f)
		{
			continue;
		}
		B.UpgradeLeft -= Dt;
		if (B.UpgradeLeft <= 0.f)
		{
			B.UpgradeLeft = -1.f;
			++B.Level;
			ApplyLevel(B, B.Kind == EVLBuilding::Castle);       // the castle's new walls come up whole
			UE_LOG(LogSovereignRealms, Log, TEXT("upgrade done: %s of team %d is level %d"), *B.Name, B.Team, B.Level);
			if (B.Team == Player)
			{
				const FVector At = B.Actor->GetActorLocation();
				PushAlert(FString::Printf(TEXT("%s raised to level %d"), *B.Name, B.Level), EVLAlert::Good, &At);
				Play2D(TEXT("S_RecruitReady"), 0.4f);
			}
		}
	}
}

FString UVLBattle::Describe(const FVLBuildingState& B) const
{
	if (B.IsSite())
	{
		return FString::Printf(TEXT("Being built: %d%% (%d Builder%s at work)"), FMath::FloorToInt(B.Build * 100.f), B.BuildersAt, B.BuildersAt == 1 ? TEXT("") : TEXT("s"));
	}
	const VLRules::FLevel& L = VLRules::Level(B.Kind, B.Level);
	switch (B.Kind)
	{
	case EVLBuilding::Castle:
		return FString::Printf(TEXT("Houses %d, troop ceiling %d, stores %d each; %d archer(s) on the walls (%.0f a shot)"), L.Housing, L.Ceiling, L.Storage, L.Archers, L.Damage);
	case EVLBuilding::Farm:
		return FString::Printf(TEXT("+%d food every %.0f s, houses %d troops"), L.Yield, VLRules::PayoutInterval, L.Housing);
	case EVLBuilding::Mine:
		return FString::Printf(TEXT("+%d gold every %.0f s"), L.Yield, VLRules::PayoutInterval);
	case EVLBuilding::Tower:
		return FString::Printf(TEXT("Shoots %.0f every %.2f s to %.0f m; %d archers of its own on the lookout; more can man it"), L.Damage, L.Interval, L.Range / 100.f, VLRules::TowerGuards(B.Level));
	case EVLBuilding::Barracks:
	case EVLBuilding::Range:
		return FString::Printf(TEXT("Trains %s (%d food, %.1f s each)"), TroopFor(B.Actor.Get()) == TEXT("Archer") ? TEXT("archers") : TEXT("swordsmen"), VLRules::Troop(TroopFor(B.Actor.Get())).Cost.Food, TrainSeconds(B.Actor.Get()));
	case EVLBuilding::Granary:
		return FString::Printf(TEXT("Holds %d food on top of the castle's stores"), L.Storage);
	case EVLBuilding::Treasury:
		return FString::Printf(TEXT("Holds %d gold on top of the castle's stores"), L.Storage);
	default:
		return FString();
	}
}

// ------------------------------------------------------------------------------------------------ towers and the castle

void UVLBattle::TickDefence(float Dt)
{
	UWorld* World = GetWorld();
	UVLArrows* Arrows = UVLArrows::Get(this);
	if (!World || !Arrows)
	{
		return;
	}
	// (the living, gathered only once a tower or a castle is due to shoot)
	FVLUnits All;
	bool bGathered = false;
	for (FVLBuildingState& B : Buildings)
	{
		AActor* A = B.Actor.Get();
		if (!B.IsWorking() || (B.Kind != EVLBuilding::Tower && B.Kind != EVLBuilding::Castle))
		{
			continue;           // (a site, or one under repair, holds its fire)
		}
		const VLRules::FLevel& L = VLRules::Level(B.Kind, B.Level);
		B.Defence -= Dt;
		if (B.Defence > 0.f || L.Archers <= 0 || L.Damage <= 0.f)
		{
			continue;
		}
		// the foes in reach of its walls, nearest first: each archer on top looses at the next of them
		if (!bGathered)
		{
			bGathered = true;
			for (AVLKing* U : AllUnits())
			{
				if (U->IsAlive())
				{
					All.Add(U);
				}
			}
		}
		TArray<TPair<float, AVLKing*>, TInlineAllocator<32>> InReach;
		for (AVLKing* U : All)
		{
			if (U->Team == B.Team || U->Team < 0)
			{
				continue;
			}
			const float D = DistanceTo(A, U->GetFeet());
			if (IsNoticed(U, D, L.Range))          // (a Spy: only inside 45% of their reach)
			{
				InReach.Add({ D, U });
			}
		}
		if (InReach.Num() == 0)
		{
			B.Defence = 0.25f;
			continue;
		}
		InReach.Sort([](const TPair<float, AVLKing*>& X, const TPair<float, AVLKing*>& Y) { return X.Key < Y.Key; });
		B.Defence = L.Interval * FMath::FRandRange(0.9f, 1.1f);
		FVector Origin, Extent;
		A->GetActorBounds(true, Origin, Extent);
		for (int32 k = 0; k < L.Archers; ++k)
		{
			AVLKing* Mark = InReach[k % InReach.Num()].Value;
			// the castle's archers stand on its corners (the one nearest the mark looses); the tower's on its top
			FVector Muzzle(Origin.X, Origin.Y, Origin.Z + Extent.Z * 0.7f);
			if (B.Kind == EVLBuilding::Castle)
			{
				const FVector To = Mark->GetActorLocation() - Origin;
				Muzzle = Origin + FVector(FMath::Sign(To.X) * Extent.X * 0.8f, FMath::Sign(To.Y) * Extent.Y * 0.8f, Extent.Z * 0.5f);
			}
			// aimed where the mark will be when the arrow gets there
			const float Speed = 5200.f;
			FVector Aim = Mark->GetActorLocation() + FVector(0.f, 0.f, 10.f);
			Aim += Mark->GetVelocity() * (FVector::Dist(Muzzle, Aim) / Speed);
			const float Gravity = UVLArrows::ArcGravity(float(FVector::Dist2D(Muzzle, Aim)), Speed, 980.f, 50.f, 2000.f, 1.f);
			FVector Dir;
			UVLArrows::SolveArc(Muzzle, Aim, Speed, Gravity, Dir);
			Muzzle += Dir * 120.f;          // (out from the walls)
			Arrows->FireFrom(A, B.Team, Muzzle, Dir * Speed, Gravity, L.Damage);
		}
	}
}

// ------------------------------------------------------------------------------------------------ the towers' own archers

void UVLBattle::TickTowerGuards(float Dt)
{
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Command)
	{
		return;
	}
	for (int32 i = 0; i < Buildings.Num(); ++i)
	{
		{
			FVLBuildingState& B = Buildings[i];
			AActor* A = B.Actor.Get();
			if (B.Kind != EVLBuilding::Tower || !A || !UVLCommand::IsTower(A))
			{
				continue;
			}
			if (!B.IsAlive() || B.Team < 0)
			{
				DismissTowerGuards(B);
				continue;
			}
			// the fallen are struck off; one of another side now (vl.SetTeam) goes; one brought down is put back up
			for (int32 k = B.Guards.Num() - 1; k >= 0; --k)
			{
				AVLKing* G = B.Guards[k].Get();
				if (!G || G->IsDead())
				{
					B.Guards.RemoveAt(k);
					continue;
				}
				if (G->Team != B.Team || (G->GarrisonIn.Get() != A && !Command->PutOnLookout(G, A)))
				{
					Command->Dismiss({ G });
					B.Guards.RemoveAt(k);
				}
			}
			// they shoot as far as the tower does (its level's reach from its walls; they stand inside them)
			const float Reach = VLRules::Level(EVLBuilding::Tower, B.Level).Range + 300.f;
			for (const TWeakObjectPtr<AVLKing>& G : B.Guards)
			{
				if (UVLArcherCombat* Bow = UVLArcherCombat::For(G.Get(), false))
				{
					Bow->TowerRange = Reach;
				}
			}
			if (!B.IsWorking())
			{
				continue;               // (a site has none yet; one under repair is not restocked meanwhile)
			}
		}
		// a tower that has just gone up is manned at once, and one raised a level gets its extra archer at once; a
		// fallen one is replaced after a while, one at a time
		const int32 Want = VLRules::TowerGuards(Buildings[i].Level);
		if (Buildings[i].GuardLevel < Buildings[i].Level)
		{
			Buildings[i].GuardLevel = Buildings[i].Level;
			Buildings[i].GuardRestock = VLRules::TowerGuardRestock;
			for (int32 Tries = 0; Buildings[i].Guards.Num() < Want && Tries < 4; ++Tries)
			{
				if (!SpawnTowerGuard(i))
				{
					break;              // (no post free on the lookout)
				}
			}
			continue;
		}
		FVLBuildingState& B = Buildings[i];
		if (B.Guards.Num() >= Want)
		{
			B.GuardRestock = VLRules::TowerGuardRestock;      // (the clock starts at the next loss)
			continue;
		}
		B.GuardRestock -= Dt;
		if (B.GuardRestock <= 0.f)
		{
			B.GuardRestock = VLRules::TowerGuardRestock;
			SpawnTowerGuard(i);
		}
	}
}

bool UVLBattle::SpawnTowerGuard(int32 Slot)
{
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Command || !Buildings.IsValidIndex(Slot))
	{
		return false;
	}
	AActor* A = Buildings[Slot].Actor.Get();
	const int32 Team = Buildings[Slot].Team;
	if (!A || Command->FreePosts(A) == 0)
	{
		return false;
	}
	FVector Door, Rally, Front;
	FrontOf(A, Door, Rally, Front);
	AVLTroop* T = SpawnTroop(TEXT("Archer"), Team, Door, Front.Rotation().Yaw);
	if (!T)
	{
		return false;
	}
	T->bTowerGuard = true;
	T->RefreshSilhouette();         // (a tower's own archer never leaves it: no outline through walls; the HUD leaves its diamond out too)
	const FString Prefix = Team == Enemy ? TEXT("Enemy ") : TEXT("");
	--Numbers.FindOrAdd(Prefix + TEXT("Archer"));      // (its own count: the trained archers' names run on without a gap)
	T->SetDisplayName(FString::Printf(TEXT("%sTower Archer %d"), *Prefix, ++Numbers.FindOrAdd(Prefix + TEXT("Tower Archer"))));
	if (UVLArcherCombat* Bow = UVLArcherCombat::For(T, true))
	{
		Bow->TowerRange = VLRules::Level(EVLBuilding::Tower, Buildings.IsValidIndex(Slot) ? Buildings[Slot].Level : 1).Range + 300.f;
	}
	if (!Command->PutOnLookout(T, A))
	{
		Command->Dismiss({ T });
		return false;
	}
	if (Buildings.IsValidIndex(Slot))     // (the spawn may have grown the list: by index)
	{
		Buildings[Slot].Guards.Add(T);
		UE_LOG(LogSovereignRealms, Log, TEXT("%s takes post on %s (team %d, %d of %d)"), *T->GetDisplayName(), *Buildings[Slot].Name, Team,
			Buildings[Slot].Guards.Num(), VLRules::TowerGuards(Buildings[Slot].Level));
	}
	return true;
}

void UVLBattle::DismissTowerGuards(FVLBuildingState& B)
{
	if (B.Guards.Num() == 0)
	{
		return;
	}
	TArray<AVLKing*> Going;
	for (const TWeakObjectPtr<AVLKing>& G : B.Guards)
	{
		if (G.IsValid() && G->IsAlive())
		{
			Going.Add(G.Get());
		}
	}
	B.Guards.Reset();
	B.GuardLevel = 0;
	if (UVLCommand* Command = UVLCommand::Get(this); Command && Going.Num() > 0)
	{
		Command->Dismiss(Going);
		UE_LOG(LogSovereignRealms, Log, TEXT("%s: its %d archers are gone with it"), *B.Name, Going.Num());
	}
}

// ------------------------------------------------------------------------------------------------ fighting on their own

void UVLBattle::GetUnits(int32 Team, TArray<AVLKing*>& Out, bool bTroopsOnly) const
{
	Out.Reset();
	for (AVLKing* U : AllUnits())
	{
		// (troops: the army; a tower's own archers are the tower's, not the army's)
		if (U->IsAlive() && U->Team == Team && (!bTroopsOnly || (U->IsTroop() && !U->bTowerGuard)))
		{
			Out.Add(U);
		}
	}
}

AActor* UVLBattle::FindFoe(const AVLKing* U, float Range, bool bUnitsOnly) const
{
	// the units that can be within Range of it (the hash), in the registry's order: the walk below picks as it did
	// over every unit (a foe further than Range is never chosen)
	// (Windows pass, batch 1: those FindFoeIn would pass over anyway, its own side and the dead, are left out as the
	// hash is read, before they are sorted; the ones it weighs are the same, in the same order)
	FVLUnits Near;
	const FVector At = U->GetActorLocation();
	const float R = FMath::Max(Range, 0.f);
	UnitsInBox(FVector2D(At.X - R, At.Y - R), FVector2D(At.X + R, At.Y + R), Near, CVarOptFoeScan.GetValueOnGameThread() != 0 ? U->Team : MIN_int32);
	return FindFoeIn(U, Range, bUnitsOnly, Near);
}

AActor* UVLBattle::FindFoeIn(const AVLKing* U, float Range, bool bUnitsOnly, const TArrayView<AVLKing* const>& Among) const
{
	const FVector Me = U->GetFeet();
	const bool bMelee = !U->IsRanged();
	AActor* Best = nullptr;
	float BestD = FMath::Square(Range);
	// a hard-to-notice foe (the Spy) is noticed at its share of the unit's sight, not of how far it goes for foes
	// (so 7.6 m from a swordsman, as before the longer reach); from a lookout, of the bow's reach
	const float NoticeBase = U->IsGarrisoned() ? Range : FMath::Min(Range, U->KindRules().Sight);
	for (const AVLKing* F : Among)
	{
		if (!F->IsAlive() || F->Team == U->Team || F->Team < 0 || (bMelee && F->IsGarrisoned()))
		{
			continue;               // (a swordsman cannot reach an archer on a lookout)
		}
		const FVector Feet = F->GetFeet();
		const float D = FVector::DistSquared2D(Feet, Me);
		if (F->KindRules().Notice < 1.f && D > FMath::Square(NoticeBase * F->KindRules().Notice))
		{
			continue;               // reduced visibility: a Spy is only noticed from close by
		}
		if (D < BestD && FMath::Abs(Feet.Z - Me.Z) < (bMelee ? 900.f : 2500.f))       // (an archer on a lookout is 14 m up)
		{
			BestD = D;
			Best = const_cast<AVLKing*>(F);
		}
	}
	if (Best || bUnitsOnly || U->IsGarrisoned())
	{
		return Best;
	}
	// troops before buildings
	float BestB = Range;
	const bool bQuick = CVarOptFoeScan.GetValueOnGameThread() != 0;
	for (const FVLBuildingState& B : Buildings)
	{
		if (!B.IsAlive() || B.Team == U->Team || B.Team < 0)
		{
			continue;
		}
		// (a building whose bounds are all further off than the best so far cannot be nearer: its exact distance,
		// to its turned box, is not worked out. The bounds' sphere holds the whole mesh.)
		const AActor* Act = B.Actor.Get();
		if (bQuick && Act)
		{
			if (const UStaticMeshComponent* Root = Cast<UStaticMeshComponent>(Act->GetRootComponent()))
			{
				const FBoxSphereBounds& Bounds = Root->Bounds;
				if (float(FVector::Dist2D(Bounds.Origin, Me)) - float(Bounds.SphereRadius) - 2.f >= BestB)
				{
					continue;
				}
			}
		}
		const float D = DistanceTo(B.Actor.Get(), Me);
		if (D < BestB)
		{
			BestB = D;
			Best = B.Actor.Get();
		}
	}
	return Best;
}

void UVLBattle::Engage(AVLKing* Unit, AActor* Target)
{
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Command || !Unit || !Target)
	{
		return;
	}
	const bool bWasAttackMove = Unit->bAttackMove;
	const double Now = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
	if ((!Unit->HasOrder() || bWasAttackMove) && Now - Unit->LastAutoFightTime > 6.0)
	{
		Unit->Post = Unit->GetFeet();       // (straight from another fight of its own: it keeps the post it had)
	}
	TGuardValue<bool> Inner(Command->bInnerOrder, true);    // its own fight: a patrol, a guard or a hold goes on
	if (Command->OrderAttack({ Unit }, Target, false, false) > 0)
	{
		Unit->bAutoAttack = true;
		if (BattleLog())
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("%s goes for %s"), *Unit->GetDisplayName(), *Target->GetName());
		}
	}
}

void UVLBattle::TickAutoCombat(float Dt)
{
	AutoTimer -= Dt;
	if (AutoTimer > 0.f)
	{
		return;
	}
	AutoTimer = 0.25f;
	UWorld* World = GetWorld();
	UVLCommand* Command = UVLCommand::Get(this);
	if (!World || !Command)
	{
		return;
	}
	const double Now = World->GetTimeSeconds();
	FVLOptTiming::FScope Timing(FVLOptTiming::AutoCombat);
	RefreshUnitHash();          // (a king may just have risen at his castle)
	// (as it was: everyone looks in the same frame, the living of this moment)
	FVLUnits Living;
	for (AVLKing* U : AllUnits())
	{
		if (U->IsAlive() && U->Team >= 0)
		{
			Living.Add(U);
		}
	}
	for (AVLKing* U : Living)
	{
		if (InPlayersHands(U) || !UVLCommand::CanAttack(U))
		{
			continue;
		}
		const VLRules::FTroop& R = U->KindRules();
		const UVLArcherCombat* Bow = UVLArcherCombat::For(U, false);
		const float BowReach = Bow ? (U->IsGarrisoned() ? Bow->TowerRange : Bow->Range) : 0.f;
		// what it notices and goes for (40 m, archers 42 m; on a lookout its bow's reach), and what it can strike from
		// where it stands
		const float Sight = U->IsGarrisoned() ? BowReach : R.Acquire;
		const float Reach = U->IsRanged() ? BowReach : 240.f;
		// a defensive unit goes for what it can strike without going further than its leash from its post
		const bool bDefensive = U->Stance == EVLStance::Defensive && !U->IsGarrisoned();
		const float DefRange = FMath::Min(Sight, VLRules::DefensiveLeash + Reach);
		bool bAttacking = false;
		AActor* Current = CombatTarget(U, &bAttacking);
		if (bAttacking)
		{
			if (!U->bAutoAttack || !Current)
			{
				continue;       // an order: obeyed, not second-guessed
			}
			U->LastAutoFightTime = Now;
			// fighting a building of its own accord: a troop that comes into sight comes first
			if (!Cast<AVLKing>(Current))
			{
				// (at a castle's walls on its commander's order: only a foe at its side, or one that struck it, draws it
				// off: with every troop in 40 m coming first, a siege fought the defenders' recruits for thirteen
				// minutes and never touched the walls)
				AActor* Striker = U->LastStruckBy.Get();
				const bool bStruck = Striker && Now - U->LastStruckTime < 3.0 && IsHostile(Striker, U->Team) && DistanceTo(Striker, U->GetFeet()) < 1500.f;
				if (AActor* Foe = U->bSiege ? (bStruck ? Striker : FindFoe(U, U->IsRanged() ? 1200.f : 700.f, true)) : FindFoe(U, U->IsHolding() ? Reach : (bDefensive ? DefRange : Sight), true))
				{
					Engage(U, Foe);
					continue;
				}
			}
			// let go by its stance: a defensive unit goes no further than its leash (20 m) from its post, then back;
			// an aggressive one gives up a chase at 1.5 times its reach (60 m) unless it is being struck
			const float FromPost = FVector::Dist2D(U->GetFeet(), U->Post);
			const float ToFoe = DistanceTo(Current, U->GetFeet());
			// (one on an attack-move, following, guarding or on a chain: its order brings it back, not its post)
			const bool bFree = !U->bAttackMove && !U->IsGarrisoned() && !Command->FollowedBy(U) && !Command->GuardWardOf(U) && !Command->HasChain(U);
			auto BackToPost = [&]()
			{
				if (bFree && FromPost > 600.f)
				{
					TGuardValue<bool> Inner(Command->bInnerOrder, true);
					Command->OrderMove({ U }, U->Post, false, EVLFormation::Line);
				}
			};
			if (bDefensive && FromPost > VLRules::DefensiveLeash)
			{
				Command->StopAttack(U);
				U->bAutoAttack = false;
				TGuardValue<bool> Inner(Command->bInnerOrder, true);
				Command->OrderMove({ U }, U->Post, false, EVLFormation::Line);
			}
			// holding its ground: it lets go of a foe that is no longer in reach, and steps back to where it stood
			else if (U->IsHolding() && !U->IsGarrisoned() && ToFoe > (U->IsRanged() ? BowReach : 240.f) * 1.25f && Now - U->LastStruckTime > 1.0)
			{
				Command->StopAttack(U);
				U->bAutoAttack = false;
				if (FVector::Dist2D(U->GetFeet(), U->Post) > 150.f)
				{
					TGuardValue<bool> Inner(Command->bInnerOrder, true);
					Command->OrderMove({ U }, U->Post, false, EVLFormation::Line);
				}
			}
			// an aggressive one gone too far from where it took the fight up: back there (not while it is being struck)
			else if (U->Stance == EVLStance::Aggressive && bFree && FromPost > VLRules::AggressiveLeash && Now - U->LastStruckTime > 2.0)
			{
				Command->StopAttack(U);
				U->bAutoAttack = false;
				BackToPost();
			}
			// (a hard-to-notice foe, the Spy, slips away at its share of that distance)
			else if (ToFoe > FMath::Max(Sight * VLRules::ChaseLetGo, BowReach * 1.2f) * (Cast<AVLKing>(Current) ? Cast<AVLKing>(Current)->KindRules().Notice : 1.f)
				&& Now - U->LastStruckTime > 4.0)
			{
				Command->StopAttack(U);
				U->bAutoAttack = false;
				BackToPost();       // (and back to where it took the fight up, not on to the next foe from there)
			}
			continue;
		}
		U->bAutoAttack = false;
		if (U->HasOrder() && !U->bAttackMove)
		{
			continue;           // a plain move ignores foes
		}
		// Hold: only what is already in reach. Defensive: what it can strike within its leash. Otherwise anything in
		// its reach (40 / 42 m); first whoever struck it
		const bool bHold = U->IsHolding();
		const float Range = bHold ? Reach : (bDefensive ? DefRange : Sight);
		AActor* Target = nullptr;
		AActor* Striker = U->LastStruckBy.Get();
		if (Striker && Now - U->LastStruckTime < 3.0 && IsHostile(Striker, U->Team) && DistanceTo(Striker, U->GetFeet()) < (bHold ? Range : FMath::Max(Range * 1.5f, BowReach))
			&& !(Cast<AVLKing>(Striker) && Cast<AVLKing>(Striker)->IsGarrisoned() && !U->IsRanged()))
		{
			Target = Striker;
		}
		if (!Target)
		{
			Target = FindFoe(U, Range);
		}
		// a friend in a fight close by (within its reach): it goes for that friend's foe, or whoever struck the friend,
		// if that is no more than VLRules::AssistExtra further. Not while holding its ground
		if (!Target && !bHold && !U->IsGarrisoned())
		{
			FVLUnits Near;
			UnitsNear(U->GetActorLocation(), Range, Near);
			float BestD = FMath::Square(Range);
			for (AVLKing* F : Near)
			{
				if (F == U || !F->IsAlive() || F->Team != U->Team)
				{
					continue;
				}
				const float D = FVector::DistSquared2D(F->GetActorLocation(), U->GetActorLocation());
				if (D >= BestD)
				{
					continue;
				}
				bool bFighting = false;
				AActor* Foe = CombatTarget(F, &bFighting);
				if (!bFighting || !Foe || !IsHostile(Foe, U->Team))
				{
					Foe = (F->LastStruckBy.IsValid() && Now - F->LastStruckTime < 3.0 && IsHostile(F->LastStruckBy.Get(), U->Team)) ? F->LastStruckBy.Get() : nullptr;
				}
				const AVLKing* FoeUnit = Cast<AVLKing>(Foe);
				if (!Foe || (FoeUnit && FoeUnit->IsGarrisoned() && !U->IsRanged()) || DistanceTo(Foe, U->GetFeet()) > Range + VLRules::AssistExtra)
				{
					continue;
				}
				BestD = D;
				Target = Foe;
			}
			if (Target && BattleLog())
			{
				UE_LOG(LogSovereignRealms, Log, TEXT("%s comes to help against %s"), *U->GetDisplayName(), *Target->GetName());
			}
		}
		// on guard: only what comes near its ward (a foe that struck it: a little further)
		float Leash = 0.f;
		if (const AActor* Ward = Target ? Command->GuardWardOf(U, &Leash) : nullptr)
		{
			FVector WardAt = Ward->GetActorLocation();
			if (const AVLKing* WardUnit = Cast<AVLKing>(Ward))
			{
				WardAt = WardUnit->GetFeet();
			}
			const float FromWard = Cast<AVLKing>(Ward) ? DistanceTo(Target, WardAt) : FMath::Min(DistanceTo(Target, WardAt), DistanceTo(Ward, Target->GetActorLocation()));
			if (FromWard > Leash * (Target == Striker ? 1.8f : 0.85f))
			{
				Target = nullptr;
			}
		}
		if (Target)
		{
			Engage(U, Target);
		}
		else if (bDefensive && !U->HasOrder() && Now - U->LastAutoFightTime < 6.0 && FVector::Dist2D(U->GetFeet(), U->Post) > 600.f && !U->bAttackMove
			&& !Command->FollowedBy(U) && !Command->GuardWardOf(U) && !Command->HasChain(U))
		{
			// a defensive unit whose fight is over (no foe left in its reach): back to its post
			U->LastAutoFightTime = -100.0;
			TGuardValue<bool> Inner(Command->bInnerOrder, true);
			Command->OrderMove({ U }, U->Post, false, EVLFormation::Line);
		}
	}
}

// ------------------------------------------------------------------------------------------------ platoons keep together

namespace
{
	/** A platoon member the cohesion reckons with: a fighter in the field (no Builder or Spy, nobody on a lookout or
	 *  on the way to one, none of a tower's own archers). */
	bool CohesionMember(const AVLKing* U)
	{
		return U && U->IsAlive() && UVLCommand::CanAttack(U) && !U->bTowerGuard && !U->IsGarrisoned() && !U->PendingGarrison.IsValid();
	}
}

void UVLBattle::NoteOrdered(const TArray<AVLKing*>& Units)
{
	const UVLCommand* Command = UVLCommand::Get(this);
	if (!Command || Command->bInnerOrder || Units.Num() == 0)
	{
		return;
	}
	TArray<AVLKing*> Members;
	for (int32 P = 0; P < UVLCommand::MaxPlatoons; ++P)
	{
		Command->GetPlatoon(P, Members);
		bool bAny = false, bAll = true;
		for (const AVLKing* M : Members)
		{
			if (CohesionMember(M) && !InPlayersHands(M))
			{
				const bool bIn = Units.Contains(M);
				bAny |= bIn;
				bAll &= bIn;
			}
		}
		if (!bAny)
		{
			continue;
		}
		for (AVLKing* M : Members)
		{
			if (bAll || Units.Contains(M))
			{
				FVLCohesion& C = Cohesion.FindOrAdd(M);
				C.Platoon = P;
				C.bApart = !bAll;       // the whole platoon ordered: together again; some of it: those are apart on purpose
				C.bSent = false;
			}
		}
	}
}

void UVLBattle::TickCohesion(float Dt)
{
	CohesionTimer -= Dt;
	if (CohesionTimer > 0.f)
	{
		return;
	}
	CohesionTimer = 0.5f;
	UWorld* World = GetWorld();
	UVLCommand* Command = UVLCommand::Get(this);
	if (!World || !Command)
	{
		return;
	}
	const double Now = World->GetTimeSeconds();
	for (auto It = Cohesion.CreateIterator(); It; ++It)
	{
		if (!It.Key().IsValid() || !It.Key()->IsAlive())
		{
			It.RemoveCurrent();
		}
	}
	struct FOne
	{
		AVLKing* Unit;
		FVLCohesion* State;
		FVector Feet;
		bool bFighting;
		bool bNew;
	};
	TArray<AVLKing*> Members;
	TArray<FOne, TInlineAllocator<32>> Body;
	for (int32 P = 0; P < UVLCommand::MaxPlatoons; ++P)
	{
		Command->GetPlatoon(P, Members);
		Body.Reset();
		for (AVLKing* M : Members)
		{
			if (!CohesionMember(M) || Command->PlatoonIndexOf(M) != P)
			{
				continue;
			}
			FVLCohesion& C = Cohesion.FindOrAdd(M);
			const bool bNew = C.Platoon != P;
			if (bNew)
			{
				C = FVLCohesion();
				C.Platoon = P;
			}
			bool bFighting = false;
			CombatTarget(M, &bFighting);
			Body.Add({ M, &C, M->GetFeet(), bFighting, bNew });
		}
		if (Body.Num() < 2)
		{
			continue;
		}
		// ---- the body: the member (not apart on purpose) with the most of the others near it; the leader on a tie
		const AVLKing* Leader = Command->GetPlatoonLeader(P);
		int32 Anchor = INDEX_NONE, AnchorNear = -1;
		for (int32 i = 0; i < Body.Num(); ++i)
		{
			if (Body[i].State->bApart)
			{
				continue;
			}
			int32 Near = 0;
			for (int32 j = 0; j < Body.Num(); ++j)
			{
				Near += (j != i && !Body[j].State->bApart && FVector::DistSquared2D(Body[i].Feet, Body[j].Feet) < FMath::Square(VLRules::CohesionBody)) ? 1 : 0;
			}
			if (Near > AnchorNear || (Near == AnchorNear && Body[i].Unit == Leader))
			{
				Anchor = i;
				AnchorNear = Near;
			}
		}
		if (Anchor == INDEX_NONE)
		{
			continue;               // (every one of them is off on an order of its own)
		}
		const FVector AnchorAt = Body[Anchor].Feet;
		for (FOne& B : Body)
		{
			FVLCohesion& C = *B.State;
			// a newcomer far from the body (a platoon formed from troops standing apart, a recruit on its way) is apart
			// on purpose until it has come to the body
			if (B.bNew && FVector::DistSquared2D(B.Feet, AnchorAt) > FMath::Square(VLRules::RegroupLeash))
			{
				C.bApart = true;
			}
			// apart on purpose, and now standing with the body again: one of it
			else if (C.bApart && !B.Unit->IsOnOrder() && !B.bFighting)
			{
				for (const FOne& O : Body)
				{
					if (O.Unit != B.Unit && !O.State->bApart && FVector::DistSquared2D(O.Feet, B.Feet) < FMath::Square(VLRules::CohesionLeash))
					{
						C.bApart = false;
						break;
					}
				}
			}
			// sent to the platoon's fight: its post stays where it stood, so its leash is measured from there; once it
			// has met a foe (or has arrived) it is no longer on an attack-move, and its stance has it again
			if (C.bSent)
			{
				B.Unit->Post = C.Home;
				if (B.bFighting || !B.Unit->HasOrder())
				{
					B.Unit->bAttackMove = false;
				}
				if (!B.bFighting && !B.Unit->IsOnOrder())
				{
					C.bSent = false;
				}
			}
		}
		// ---- those standing idle away from the fight, or from the body
		for (FOne& B : Body)
		{
			AVLKing* M = B.Unit;
			FVLCohesion& C = *B.State;
			TArray<FVector> RoutePoints;
			bool bLoop = false;
			int32 RouteNext = 0;
			if (C.bApart || B.bFighting || M->IsOnOrder() || M->Stance != EVLStance::Aggressive || M->IsHolding() || M->KindId() == EVLUnitKind::King || InPlayersHands(M)
				|| Now - C.SentAt < 2.0 || Command->FollowedBy(M) || Command->GuardWardOf(M) || Command->HasChain(M) || Command->IsRoaming(M)
				|| Command->GetRoute(M, RoutePoints, bLoop, RouteNext))
			{
				continue;
			}
			// the nearest member in a fight (those apart on purpose fight their own)
			const FOne* Fight = nullptr;
			float FightD = TNumericLimits<float>::Max();
			for (const FOne& O : Body)
			{
				if (O.Unit != M && O.bFighting && !O.State->bApart)
				{
					const float D = float(FVector::Dist2D(O.Feet, B.Feet));
					if (D < FightD)
					{
						FightD = D;
						Fight = &O;
					}
				}
			}
			if (Fight)
			{
				if (FightD <= VLRules::CohesionLeash)
				{
					continue;       // near the fight: what it goes for is its own look-out (UVLBattle::TickAutoCombat)
				}
				// to the fight, fighting what it meets on the way; no further than its stance lets it go from here
				FVector Dest = Fight->Feet;
				const FVector2D Way(Dest - B.Feet);
				if (Way.Size() > VLRules::AggressiveLeash)
				{
					const FVector2D To = FVector2D(B.Feet) + Way.GetSafeNormal() * VLRules::AggressiveLeash;
					Dest = FVector(To.X, To.Y, B.Feet.Z);
				}
				C.SentAt = Now;
				C.bSent = true;
				C.Home = B.Feet;
				{
					TGuardValue<bool> Inner(Command->bInnerOrder, true);
					AttackMove({ M }, Dest, true, uint8(EVLFormation::Line));
				}
				if (BattleLog())
				{
					UE_LOG(LogSovereignRealms, Log, TEXT("cohesion: %s of platoon %d runs to join %s, %.0f m off"), *M->GetDisplayName(), P + 1, *Fight->Unit->GetDisplayName(), FightD / 100.f);
				}
				continue;
			}
			// no fight: back to the body when it has ended up far from it
			if (&B != &Body[Anchor] && FVector::DistSquared2D(B.Feet, AnchorAt) > FMath::Square(VLRules::RegroupLeash))
			{
				C.SentAt = Now;
				{
					TGuardValue<bool> Inner(Command->bInnerOrder, true);
					Command->OrderMove({ M }, AnchorAt, false, EVLFormation::Line);
				}
				if (BattleLog())
				{
					UE_LOG(LogSovereignRealms, Log, TEXT("cohesion: %s of platoon %d walks back to its platoon, %.0f m off"), *M->GetDisplayName(), P + 1, FVector::Dist2D(B.Feet, AnchorAt) / 100.f);
				}
			}
		}
	}
}

void UVLBattle::LogCohesion() const
{
	const UVLCommand* Command = UVLCommand::Get(this);
	if (!Command)
	{
		return;
	}
	TArray<AVLKing*> Members;
	for (int32 P = 0; P < UVLCommand::MaxPlatoons; ++P)
	{
		Command->GetPlatoon(P, Members);
		if (Members.Num() == 0)
		{
			continue;
		}
		FVector2D Min(1e9f, 1e9f), Max(-1e9f, -1e9f);
		for (const AVLKing* M : Members)
		{
			const FVector2D At(M->GetFeet());
			Min = FVector2D::Min(Min, At);
			Max = FVector2D::Max(Max, At);
		}
		UE_LOG(LogSovereignRealms, Log, TEXT("cohesion: platoon %d, %d member(s), %s, spread %.0f m"), P + 1, Members.Num(), UVLCommand::StanceName(Command->PlatoonStance(P)), (Max - Min).Size() / 100.f);
		for (AVLKing* M : Members)
		{
			const FVLCohesion* C = Cohesion.Find(M);
			bool bFighting = false;
			CombatTarget(M, &bFighting);
			UE_LOG(LogSovereignRealms, Log, TEXT("  %s at %s: %s%s%s%s speed %.0f"), *M->GetDisplayName(), *M->GetFeet().ToCompactString(), bFighting ? TEXT("fighting") : (M->IsOnOrder() ? TEXT("walking") : TEXT("idle")),
				!CohesionMember(M) ? TEXT(", not reckoned with") : TEXT(""), C && C->bApart ? TEXT(", apart on purpose") : TEXT(""), C && C->bSent ? TEXT(", sent to the fight") : TEXT(""),
				M->GetVelocity().Size2D());
		}
	}
}

void UVLBattle::AttackMove(const TArray<AVLKing*>& Units, const FVector& Ground, bool bRun, uint8 Shape)
{
	UVLCommand* Command = UVLCommand::Get(this);
	if (!Command || Units.Num() == 0)
	{
		return;
	}
	Command->OrderMove(Units, Ground, bRun, EVLFormation(Shape));
	for (AVLKing* U : Units)
	{
		if (U)
		{
			U->bAttackMove = true;
		}
	}
}

// ------------------------------------------------------------------------------------------------ the king

void UVLBattle::TickKings(float Dt)
{
	// (kings are few: the walk only gathers them; raising one may move it, never add or remove a unit)
	TArray<AVLKing*, TInlineAllocator<4>> Fallen;
	for (AVLKing* K : AllUnits())
	{
		if (!K->IsTroop() && K->IsDead() && K->DeadFor() >= VLRules::KingRespawnSeconds)
		{
			Fallen.Add(K);
		}
	}
	for (AVLKing* K : Fallen)
	{
		// he rises again in front of his castle (in a sandbox without one: where he came into the world)
		FVector Feet = K->Post;
		if (AActor* Castle = GetCastle(K->Team))
		{
			FVector Rally, Front;
			FrontOf(Castle, Feet, Rally, Front);
		}
		else if (bBattle)
		{
			continue;           // his castle has fallen: no more
		}
		else
		{
			if (TActorIterator<APlayerStart> P(GetWorld()); P)
			{
				Feet = P->GetActorLocation() - FVector(0.f, 0.f, 90.f);
			}
		}
		K->Revive(Feet);
		if (K->Team == Player)
		{
			PushAlert(TEXT("King David has returned to the castle"), EVLAlert::Good, &Feet);
		}
	}
}

// ------------------------------------------------------------------------------------------------ the match

const TCHAR* UVLBattle::DifficultyName(int32 InDifficulty)
{
	return InDifficulty <= 0 ? TEXT("Easy") : (InDifficulty >= 2 ? TEXT("Hard") : TEXT("Normal"));
}

FVLCommander* UVLBattle::GetCommander(int32 Team) const
{
	return (Team == 0 || Team == 1) ? Commanders[Team].Get() : nullptr;
}

void UVLBattle::SetPlayerAI(bool bOn, int32 InDifficulty)
{
	if (FVLCommander* C = Commanders[0].Get())
	{
		if (bOn)
		{
			C->Reset(this, Player, InDifficulty >= 0 ? InDifficulty : Difficulty);
			// Computer against computer (balance tests): the sides even. The player's platoons go (the commander has
			// squads; a platoon's cohesion would pull its troops about under it), and King David, whom the enemy has no
			// match for and no commander plays, is benched: nobody's (team -1, which nobody fights or counts), hidden,
			// out of the way in the sea off the map's corner. vl.AIvsAI.King 1 keeps him (he then fights by himself
			// near the castle, as an idle troop).
			if (UVLCommand* Command = UVLCommand::Get(this))
			{
				for (int32 P = 0; P < UVLCommand::MaxPlatoons; ++P)
				{
					Command->DisbandPlatoon(P);
				}
			}
			static const IConsoleVariable* KeepKing = IConsoleManager::Get().FindConsoleVariable(TEXT("vl.AIvsAI.King"));
			if (!KeepKing || KeepKing->GetInt() == 0)
			{
				for (AVLKing* K : AllUnits())
				{
					if (!K->IsTroop() && K->Team == Player)
					{
						FBox2D Bounds(FVector2D(-30000.f, -30000.f), FVector2D(30000.f, 30000.f));
						if (UVLGrid* Grid = UVLGrid::Get(this); Grid && Grid->EnsureBuilt())
						{
							Bounds = Grid->GetBounds();
						}
						K->Team = -1;
						K->SetActorHiddenInGame(true);
						K->GetCharacterMovement()->DisableMovement();      // (no collision: he would fall through the world)
						K->GetCharacterMovement()->GravityScale = 0.f;
						K->SetActorEnableCollision(false);
						K->SetActorLocation(FVector(Bounds.Min.X - 2000.f, Bounds.Min.Y - 2000.f, K->GetActorLocation().Z), false, nullptr, ETeleportType::TeleportPhysics);
						bHashDirty = true;
						UE_LOG(LogSovereignRealms, Log, TEXT("AI vs AI: %s benched (vl.AIvsAI.King 1 keeps him)"), *K->GetDisplayName());
					}
				}
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("AI vs AI: team 0 %s, team 1 %s"), DifficultyName(C->Difficulty), Commanders[1].IsValid() ? DifficultyName(Commanders[1]->Difficulty) : TEXT("-"));
		}
		C->bActive = bOn;
	}
}

void UVLBattle::StartMatch(int32 InDifficulty)
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	Difficulty = FMath::Clamp(InDifficulty, 0, 2);
	if (State != EVLMatch::Idle)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("match: already started (difficulty now %s; vl.Restart for a new one)"), DifficultyName(Difficulty));
		return;
	}
	SpyCooldownLeft[0] = SpyCooldownLeft[1] = 0.f;
	ScanBuildings();
	MatchLog.Reset();           // (a new match, a new log: vl.MatchLog)
	// (Windows pass, batch 2) the battle's sound sets, loaded as the match starts and not each at its first use in the
	// middle of it (a load on the game thread: the first arrow, the first blow, the first building to fall)
	for (const TCHAR* Base : { TEXT("S_ArrowFly"), TEXT("S_ArrowHitFlesh"), TEXT("S_ArrowHitGround"), TEXT("S_ArrowHitWood"), TEXT("S_AttackAlert"), TEXT("S_BowDraw"),
		TEXT("S_BowRelease"), TEXT("S_BuildComplete"), TEXT("S_BuildPlace"), TEXT("S_BuildingCollapse"), TEXT("S_BuildingHit"), TEXT("S_Death"), TEXT("S_RecruitReady"),
		TEXT("S_SwordHit"), TEXT("S_UIClick"), TEXT("S_UIError") })
	{
		Sounds(Base);
	}
	State = EVLMatch::Playing;
	Clock = 0.f;
	Winner = -1;
	EndedAt = -1.0;
	for (int32 t = 0; t < 2; ++t)
	{
		Kingdoms[t] = FVLKingdom();
		Kingdoms[t].Gold = VLRules::StartGold;
		Kingdoms[t].Food = VLRules::StartFood;
		Kingdoms[t].bHasCastle = GetCastle(t) != nullptr;
	}
	bBattle = Kingdoms[0].bHasCastle && Kingdoms[1].bHasCastle;
	Commanders[1]->Reset(this, Enemy, Difficulty);
	Commanders[1]->bActive = bBattle;
	Commanders[0]->bActive = false;
	if (bBattle)
	{
		// a battle starts with no barracks and no archery range on either side: Builders raise them (VLConstruction.*)
		if (UVLConstruction* Construction = UVLConstruction::Get(this))
		{
			Construction->ClearStartTrainers();
		}
		// each side's start: its castle (and what else the map has), 3 swordsmen and 2 archers in front of it by its
		// gathering point (the level's TeamStart:<team>, else Rally:<team>, else in front of the castle), and a Builder
		// beside them. King David (the player's) stands at the PlayerStart, on TeamStart:0.
		UVLGrid* Grid = UVLGrid::Get(this);
		const bool bGrid = Grid && Grid->EnsureBuilt();
		for (int32 t = 0; t < 2; ++t)
		{
			FVector Where = FVector::ZeroVector, Front = FVector::ForwardVector;
			bool bFound = false;
			const FName StartTag(*FString::Printf(TEXT("TeamStart:%d"), t)), RallyTag(*FString::Printf(TEXT("Rally:%d"), t));
			for (const FName& Tag : { StartTag, RallyTag })
			{
				for (TActorIterator<AActor> It(World); It && !bFound; ++It)
				{
					if (It->ActorHasTag(Tag))
					{
						Where = It->GetActorLocation();
						bFound = true;
					}
				}
			}
			FVector Door, CastleRally;
			FrontOf(GetCastle(t), Door, CastleRally, Front);
			if (!bFound)
			{
				Where = CastleRally;
			}
			const FVector Side(-Front.Y, Front.X, 0.f);
			// the troops a few steps out in front (the king stands on the start itself), the Builder to one side
			const FVector Centre = Where + Front * 320.f;
			TArray<FString> Kinds;
			for (int32 i = 0; i < VLRules::StartSwordsmen; ++i) { Kinds.Add(TEXT("Swordsman")); }
			for (int32 i = 0; i < VLRules::StartArchers; ++i) { Kinds.Add(TEXT("Archer")); }
			const int32 NumTroops = Kinds.Num();
			for (int32 i = 0; i < VLBuild::StartBuilders; ++i) { Kinds.Add(TEXT("Builder")); }
			TArray<AVLKing*> Army;
			for (int32 i = 0; i < Kinds.Num(); ++i)
			{
				FVector P = i < NumTroops ? Centre + Side * (((i % 3) - 1) * 140.f) + Front * ((i / 3) * 140.f)
					: Where + Side * (380.f + (i - NumTroops) * 130.f);
				if (bGrid)
				{
					const int32 Node = Grid->NearestNode(FVector(P.X, P.Y, P.Z + 300.f), 30, Grid->MainRegion());
					if (Node != INDEX_NONE)
					{
						P = Grid->NodePos(Node);
					}
				}
				if (AVLTroop* Tr = SpawnTroop(Kinds[i], t, P, Front.Rotation().Yaw); Tr && i < NumTroops)
				{
					Army.Add(Tr);
				}
			}
			if (t == Player && Army.Num() > 0)
			{
				if (UVLCommand* Command = UVLCommand::Get(this))
				{
					Command->AssignPlatoon(0, Army);        // the starting army is platoon 1 (the Builder is not in it)
				}
			}
		}
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("match started on %s: %s, difficulty %s, %d buildings"), *World->GetMapName(), bBattle ? TEXT("a battle") : TEXT("a sandbox (no enemy castle)"),
		DifficultyName(Difficulty), Buildings.Num());
}

void UVLBattle::SetupTestWorld()
{
	bTestWorld = true;
	UWorld* World = GetWorld();
	UVLConstruction* Construction = UVLConstruction::Get(this);
	UVLCommand* Command = UVLCommand::Get(this);
	UVLGrid* Grid = UVLGrid::Get(this);
	if (!World || !Construction || !bBattle || State != EVLMatch::Playing)
	{
		UE_LOG(LogSovereignRealms, Warning, TEXT("test world: no battle here (the map needs both castles)"));
		return;
	}
	const bool bGrid = Grid && Grid->EnsureBuilt();
	for (int32 t = 0; t < 2; ++t)
	{
		AActor* Castle = GetCastle(t);
		if (!Castle)
		{
			continue;
		}
		// ---- the castle at its top level (the limits, the housing, the ceiling and the stores all hang on it)
		if (FVLBuildingState* C = FindBuilding(Castle))
		{
			C->Level = VLRules::NumLevels(EVLBuilding::Castle);
			C->UpgradeLeft = -1.f;
			ApplyLevel(*C, true);
		}
		Kingdoms[t].Gold = 1000000;         // (to pay for the sites; set to the full stores below)
		// ---- its buildings, each kind on its own ring round the castle, by the construction's own placing
		FVector Door, Rally, Front;
		FrontOf(Castle, Door, Rally, Front);
		const FVector Home = Castle->GetActorLocation();
		const float FrontAngle = FMath::Atan2(Front.Y, Front.X);
		struct FWant
		{
			EVLBuilding Kind;
			int32 Count;
			float Ring;             // cm from the castle
			float Turn;             // radians: where on its ring the first goes, from the castle's front
		};
		const FWant Wants[] = {
			{ EVLBuilding::Barracks, 2, 4200.f, 0.9f }, { EVLBuilding::Range, 2, 4200.f, 2.2f }, { EVLBuilding::Granary, 1, 3400.f, 1.57f }, { EVLBuilding::Treasury, 1, 3400.f, -1.57f },
			{ EVLBuilding::Farm, 99, 5600.f, 0.35f }, { EVLBuilding::Tower, 99, 7000.f, 0.f } };
		int32 Laid = 0, Missed = 0;
		for (const FWant& W : Wants)
		{
			const int32 Limit = Construction->BuildLimit(W.Kind, t);
			const int32 N = Limit == INDEX_NONE ? W.Count : FMath::Min(W.Count, Limit - Construction->CountRaised(W.Kind, t));
			for (int32 i = 0; i < N; ++i)
			{
				const float Angle = FrontAngle + W.Turn + 2.f * PI * float(i) / float(FMath::Max(N, 1));
				const FVector Near = Home + FVector(FMath::Cos(Angle), FMath::Sin(Angle), 0.f) * W.Ring;
				// (its front away from the castle, on the quarter turns a placing has)
				const float Yaw = FMath::RoundToFloat((FMath::RadiansToDegrees(Angle) - 90.f) / 90.f) * 90.f;
				FVLPlacement Where;
				FString Why;
				// (its place on the ring; where the map has no room there, anywhere round the castle)
				const bool bFound = Construction->FindPlacementNear(W.Kind, t, Near, 5000.f, Yaw, Where, 220) || Construction->FindPlacementNear(W.Kind, t, Home, 11000.f, Yaw, Where, 700);
				AActor* Made = bFound ? Construction->PlaceBuilding(Where, {}, &Why, true) : nullptr;
				if (Made && Construction->FinishNow(Made))
				{
					++Laid;
				}
				else
				{
					++Missed;
					UE_LOG(LogSovereignRealms, Warning, TEXT("test world: no place for a %s of team %d near %.0f %.0f (%s)"), VLRules::Name(W.Kind), t, Near.X, Near.Y, Why.IsEmpty() ? TEXT("no spot") : *Why);
				}
			}
		}
		// ---- every building of the side at its top level (the map's own too: its mine, its tower)
		for (FVLBuildingState& B : Buildings)
		{
			if (B.Team == t && B.IsAlive() && !B.IsSite())
			{
				B.Level = VLRules::NumLevels(B.Kind);
				B.UpgradeLeft = -1.f;
				ApplyLevel(B, true);
			}
		}
		// ---- full stores
		Kingdoms[t].Gold = GetStorage(t, EVLRes::Gold);
		Kingdoms[t].Food = GetStorage(t, EVLRes::Food);
		// ---- troops up to the ceiling, in a block in front of the gathering point; every Builder it may have
		FVector Where = Rally;
		const FName StartTag(*FString::Printf(TEXT("TeamStart:%d"), t));
		for (TActorIterator<AActor> It(World); It; ++It)
		{
			if (It->ActorHasTag(StartTag))
			{
				Where = It->GetActorLocation();
				break;
			}
		}
		const FVector Side(-Front.Y, Front.X, 0.f);
		auto Stand = [&](const FVector& Want)
		{
			FVector P = Want;
			if (bGrid)
			{
				const int32 Node = Grid->NearestNode(FVector(P.X, P.Y, P.Z + 300.f), 40, Grid->MainRegion());
				if (Node != INDEX_NONE)
				{
					P = Grid->NodePos(Node);
				}
			}
			return P;
		};
		TArray<AVLKing*> Army;
		GetUnits(t, Army, true);
		Army.RemoveAll([](const AVLKing* U) { return U->KindRules().Pop <= 0 || !UVLCommand::CanAttack(U); });
		const int32 Had = Army.Num();
		const int32 Room = GetPopulationCap(t) - GetPopulation(t);
		const int32 Columns = 14;
		for (int32 i = 0; i < Room; ++i)
		{
			const FVector P = Stand(Where + Front * (700.f + float(i / Columns) * 150.f) + Side * ((float(i % Columns) - 0.5f * float(Columns - 1)) * 150.f));
			if (AVLTroop* Tr = SpawnTroop(i % 5 < 3 ? TEXT("Swordsman") : TEXT("Archer"), t, P, Front.Rotation().Yaw))
			{
				Army.Add(Tr);
			}
		}
		const int32 Builders = VLBuild::MaxBuilders(GetCastleLevel(t)) - Construction->CountBuilders(t);
		for (int32 i = 0; i < Builders; ++i)
		{
			SpawnTroop(TEXT("Builder"), t, Stand(Where + Side * (520.f + float(i) * 130.f) - Front * 200.f), Front.Rotation().Yaw);
		}
		if (t == Player && Command)
		{
			// the player's army in six platoons, each with swordsmen and archers (the starting five are in the first)
			const int32 Per = FMath::DivideAndRoundUp(Army.Num(), UVLCommand::MaxPlatoons);
			for (int32 P = 0; P < UVLCommand::MaxPlatoons; ++P)
			{
				TArray<AVLKing*> Members;
				for (int32 i = P * Per; i < FMath::Min((P + 1) * Per, Army.Num()); ++i)
				{
					Members.Add(Army[i]);
				}
				if (Members.Num() > 0)
				{
					Command->AssignPlatoon(P, Members);
				}
			}
		}
		UE_LOG(LogSovereignRealms, Log, TEXT("test world: team %d has its castle at level %d, %d building(s) laid (%d found no place), %d troops (%d new) of %d housed, %d Builders, %d gold and %d food"),
			t, GetCastleLevel(t), Laid, Missed, Army.Num(), Army.Num() - Had, GetPopulationCap(t), Construction->CountBuilders(t), Kingdoms[t].Gold, Kingdoms[t].Food);
	}
}

void UVLBattle::CheckEnd()
{
	if (!bBattle || State != EVLMatch::Playing)
	{
		return;
	}
	for (int32 t = 0; t < 2; ++t)
	{
		if (!GetCastle(t))
		{
			Winner = 1 - t;
			State = EVLMatch::Ended;
			EndedAt = GetWorld()->GetRealTimeSeconds();
			UE_LOG(LogSovereignRealms, Log, TEXT("match over after %s: %s castle has fallen, %s"), *ClockText(Clock), t == Player ? TEXT("the player's") : TEXT("the enemy's"),
				Winner == Player ? TEXT("VICTORY") : TEXT("DEFEAT"));
			for (FVLCommander* C : { Commanders[0].Get(), Commanders[1].Get() })
			{
				if (C)
				{
					C->bActive = false;
				}
			}
			return;
		}
	}
}

float UVLBattle::GetEndTime() const
{
	return (State == EVLMatch::Ended && EndedAt >= 0.0 && GetWorld()) ? float(GetWorld()->GetRealTimeSeconds() - EndedAt) : -1.f;
}

FString UVLBattle::EnemyStatus(FLinearColor* OutColour) const
{
	const FVLCommander* C = Commanders[1].Get();
	if (!bBattle || !C || State != EVLMatch::Playing)
	{
		return FString();
	}
	FLinearColor Col(0.75f, 0.72f, 0.62f);
	FString S;
	if (C->IsAttacking())
	{
		S = TEXT("Enemy attacking!");
		Col = FLinearColor(1.f, 0.3f, 0.2f);
	}
	else if (C->NextWaveIn() > 0.f && C->NextWaveIn() <= C->MaxWaveWait())      // (never a wait longer than it can have)
	{
		S = FString::Printf(TEXT("Enemy ready in %s"), *ClockText(C->NextWaveIn()));
		if (C->NextWaveIn() < 60.f)
		{
			Col = FLinearColor(1.f, 0.7f, 0.25f);
		}
	}
	else
	{
		S = TEXT("Enemy watching");
	}
	if (OutColour)
	{
		*OutColour = Col;
	}
	return S;
}

void UVLBattle::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	UWorld* World = GetWorld();
	if (!World || DeltaSeconds <= 0.f)
	{
		return;
	}
	FVLOptTiming::FScope Timing(FVLOptTiming::BattleTick);
	RefreshUnitHash();          // (the actors have ticked: where every unit stands now)
	if (CVarOptRegistryCheck.GetValueOnGameThread() != 0)
	{
		CheckRegistry();
	}
	TickCollapse(DeltaSeconds);
	const double Now = World->GetRealTimeSeconds();
	Alerts.RemoveAll([Now](const FVLAlert& A) { return Now - A.Time > 7.0; });
	if (State == EVLMatch::Idle)
	{
		return;
	}
	TickKings(DeltaSeconds);
	TickAutoCombat(DeltaSeconds);
	TickCohesion(DeltaSeconds);
	if (UVLCommand* Command = UVLCommand::Get(this))
	{
		Command->TickOrders(DeltaSeconds);     // patrols, attack-moves, guards, roaming Spies
	}
	TickDefence(DeltaSeconds);
	if (bBattle && !MatchLog.IsValid() && State == EVLMatch::Playing && FVLMatchLog::Wanted())
	{
		MatchLog = MakeShared<FVLMatchLog>();
	}
	if (MatchLog.IsValid())
	{
		MatchLog->Tick(this, DeltaSeconds);
	}
	FVLDuels::Tick(this, DeltaSeconds);
	if (State == EVLMatch::Ended)
	{
		static double Sounded = -1.0;
		if (GetEndTime() >= VLRules::EndScreenDelay && Sounded != EndedAt)
		{
			Sounded = EndedAt;
			Play2D(Winner == Player ? TEXT("S_Victory") : TEXT("S_Defeat"), 0.7f);
		}
		return;
	}
	Clock += DeltaSeconds;
	TickEconomy(DeltaSeconds);
	TickKingRest(DeltaSeconds);
	TickTraining(DeltaSeconds);
	TickUpgrades(DeltaSeconds);
	TickTowerGuards(DeltaSeconds);
	for (int32 t = 0; t < 2; ++t)
	{
		if (FVLCommander* C = Commanders[t].Get(); C && C->bActive)
		{
			C->Step(this, DeltaSeconds);
		}
	}
	CheckEnd();
}

// ------------------------------------------------------------------------------------------------ feedback

void UVLBattle::PushAlert(const FString& Text, EVLAlert Kind, const FVector* At)
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}
	FVLAlert A;
	A.Text = Text;
	A.Kind = Kind;
	A.bHasAt = At != nullptr;
	A.At = At ? *At : FVector::ZeroVector;
	A.Time = World->GetRealTimeSeconds();
	Alerts.Insert(A, 0);
	if (Alerts.Num() > 5)
	{
		Alerts.SetNum(5);
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("alert: %s"), *Text);
}

FVLSoundSet* UVLBattle::Sounds(const TCHAR* Base)
{
	FVLSoundSet* Set = SoundSets.Find(Base);
	if (!Set)
	{
		Set = &SoundSets.Add(Base);
		for (int32 i = 1; i <= 8; ++i)
		{
			const FString Name = i == 1 ? FString(Base) : FString::Printf(TEXT("%s_%d"), Base, i);
			// (asked first whether there is such a sound: a load of one that is not there is a search of the
			// packages and a line in the log for each)
			if (!FPackageName::DoesPackageExist(FString::Printf(TEXT("/Game/Voxel/Audio/%s"), *Name)))
			{
				continue;
			}
			if (USoundBase* S = LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/Voxel/Audio/%s.%s"), *Name, *Name), nullptr, LOAD_NoWarn | LOAD_Quiet))
			{
				Set->Sounds.Add(S);
			}
		}
		if (Set->Sounds.Num() == 0)
		{
			UE_LOG(LogSovereignRealms, Warning, TEXT("no %s sounds (copy them to SourceArt/Audio and run Tools/ue/import_audio.py)"), Base);
		}
	}
	return Set;
}

void UVLBattle::PlayAt(const TCHAR* Base, const FVector& At, float Volume, float Range, float Gap)
{
	UWorld* World = GetWorld();
	FVLSoundSet* Set = Sounds(Base);
	if (!World || !Set || Set->Sounds.Num() == 0)
	{
		return;
	}
	const double Now = World->GetTimeSeconds();
	if (Now - Set->LastTime < Gap)
	{
		return;
	}
	const APlayerController* PC = World->GetFirstPlayerController();
	const AVLKing* Me = PC ? Cast<AVLKing>(PC->GetPawn()) : nullptr;
	const float Far = Me ? FVector::Dist2D(At, Me->GetListenFocus()) : 0.f;
	const float Fade = FMath::Square(FMath::GetMappedRangeValueClamped(FVector2D(Range * 0.2f, Range), FVector2D(1.f, 0.f), Far));
	Volume *= Fade * EffectsVolume;
	if (Volume <= 0.004f)
	{
		return;
	}
	int32 Index = FMath::RandRange(0, Set->Sounds.Num() - 1);
	if (Index == Set->Last && Set->Sounds.Num() > 1)
	{
		Index = (Index + 1) % Set->Sounds.Num();
	}
	Set->Last = Index;
	Set->LastTime = Now;
	UGameplayStatics::PlaySoundAtLocation(World, Set->Sounds[Index], At, Volume, FMath::FRandRange(0.94f, 1.06f), 0.f, Pan);
}

void UVLBattle::Play2D(const TCHAR* Base, float Volume)
{
	FVLSoundSet* Set = Sounds(Base);
	if (!Set || Set->Sounds.Num() == 0)
	{
		return;
	}
	const int32 Index = FMath::RandRange(0, Set->Sounds.Num() - 1);
	UGameplayStatics::PlaySound2D(this, Set->Sounds[Index], Volume * EffectsVolume);
}

// ------------------------------------------------------------------------------------------------ tests

int32 UVLBattle::SpawnTestBase(const FVector& Offset, int32 Team)
{
	UWorld* World = GetWorld();
	if (!World)
	{
		return 0;
	}
	// one of every kind the level has, copied (its mesh, scale, tags), turned round to face the original
	TArray<AActor*> Models;
	TSet<EVLBuilding> Kinds;
	for (const FVLBuildingState& B : Buildings)
	{
		AActor* A = B.Actor.Get();
		if (A && B.Team != Team && !Kinds.Contains(B.Kind) && Cast<AStaticMeshActor>(A) && B.Kind != EVLBuilding::Hall)
		{
			Kinds.Add(B.Kind);
			Models.Add(A);
		}
	}
	FVector Centre = FVector::ZeroVector;
	for (AActor* M : Models)
	{
		Centre += M->GetActorLocation();
	}
	Centre /= FMath::Max(Models.Num(), 1);
	int32 Made = 0;
	for (AActor* M : Models)
	{
		const AStaticMeshActor* SMA = Cast<AStaticMeshActor>(M);
		UStaticMesh* Mesh = SMA->GetStaticMeshComponent()->GetStaticMesh();
		// mirrored through the middle of the originals, then moved by Offset: the two lines face each other
		const FVector Rel = M->GetActorLocation() - Centre;
		const FVector At = Centre + FVector(Rel.X, -Rel.Y, Rel.Z) + Offset;
		FActorSpawnParameters P;
		P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		AStaticMeshActor* Copy = World->SpawnActor<AStaticMeshActor>(At, M->GetActorRotation() + FRotator(0.f, 180.f, 0.f), P);
		if (!Copy)
		{
			continue;
		}
		Copy->GetStaticMeshComponent()->SetMobility(EComponentMobility::Movable);
		Copy->GetStaticMeshComponent()->SetStaticMesh(Mesh);
		Copy->SetActorScale3D(M->GetActorScale3D());
		for (const FName& Tag : M->Tags)
		{
			if (!Tag.ToString().StartsWith(TEXT("Team:")))
			{
				Copy->Tags.Add(Tag);
			}
		}
		Copy->Tags.Add(*FString::Printf(TEXT("Team:%d"), Team));
		RegisterBuilding(Copy);
		++Made;
	}
	if (UVLGrid* Grid = UVLGrid::Get(this))
	{
		Grid->Build();
	}
	// a sandbox with both castles now: a battle, with its commander
	if (State == EVLMatch::Playing && !bBattle && GetCastle(0) && GetCastle(1))
	{
		bBattle = true;
		Kingdoms[0].bHasCastle = Kingdoms[1].bHasCastle = true;
		Commanders[1]->Reset(this, Enemy, Difficulty);
		Commanders[1]->bActive = true;
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("test base: %d buildings of team %d at an offset of %s"), Made, Team, *Offset.ToCompactString());
	return Made;
}

void UVLBattle::Raze(AActor* Building)
{
	if (FVLBuildingState* B = FindBuilding(Building); B && B->IsAlive())
	{
		Collapse(*B, nullptr, B->Team, true);
	}
}

void UVLBattle::Forget(AActor* Building)
{
	Buildings.RemoveAll([Building](const FVLBuildingState& S) { return S.Actor.Get() == Building; });
	bBuildingIndexDirty = true;
	bTagsDirty = true;
}

void UVLBattle::LogStatus() const
{
	UE_LOG(LogSovereignRealms, Log, TEXT("battle: %s, %s, difficulty %s, clock %s%s"), State == EVLMatch::Idle ? TEXT("not started") : (State == EVLMatch::Playing ? TEXT("playing") : TEXT("ended")),
		bBattle ? TEXT("a battle") : TEXT("a sandbox"), DifficultyName(Difficulty), *ClockText(Clock), Winner >= 0 ? (Winner == Player ? TEXT(", the player won") : TEXT(", the enemy won")) : TEXT(""));
	for (int32 t = 0; t < 2; ++t)
	{
		const FVLKingdom& K = Kingdoms[t];
		TArray<AVLKing*> U;
		GetUnits(t, U, true);
		UE_LOG(LogSovereignRealms, Log, TEXT("team %d: %d/%d gold %d/%d food (+%.0f +%.0f a minute), troops %d (+%d queued) of %d (ceiling %d), castle level %d, recruited %d lost %d killed %d buildings lost %d"),
			t, K.Gold, GetStorage(t, EVLRes::Gold), K.Food, GetStorage(t, EVLRes::Food), GetIncomePerMinute(t, EVLRes::Gold), GetIncomePerMinute(t, EVLRes::Food), U.Num(),
			GetQueuedPopulation(t), GetPopulationCap(t), GetPopulationCeiling(t), GetCastleLevel(t), K.Recruited, K.Lost, K.Killed, K.BuildingsLost);
		if (const FVLCommander* C = Commanders[t].Get(); C && C->bActive)
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("team %d commander: %s"), t, *C->Describe());
		}
	}
	for (const FVLBuildingState& B : Buildings)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("  %-14s team %d level %d health %5.0f/%5.0f%s%s%s%s"), *B.Name, B.Team, B.Level, B.Health, B.MaxHealth, B.bDestroyed ? TEXT(" DESTROYED") : TEXT(""),
			B.IsSite() ? *FString::Printf(TEXT(", SITE %.0f%% (%d builders)"), B.Build * 100.f, B.BuildersAt) : (B.bRepairing ? TEXT(", under repair") : TEXT("")),
			B.Queue.Num() ? *FString::Printf(TEXT(", %d in training"), B.Queue.Num()) : TEXT(""), B.UpgradeLeft >= 0.f ? *FString::Printf(TEXT(", raising (%.0f s)"), B.UpgradeLeft) : TEXT(""));
	}
}

// ------------------------------------------------------------------------------------------------ console

namespace
{
	AActor* BuildingNamed(UWorld* World, const FString& Name, int32 Team = -2)
	{
		UVLBattle* Battle = UVLBattle::Get(World);
		if (!Battle)
		{
			return nullptr;
		}
		const FString Want = Name.Replace(TEXT("_"), TEXT(" "));
		for (const FVLBuildingState& B : Battle->GetBuildings())
		{
			if (B.IsAlive() && B.Name.Equals(Want, ESearchCase::IgnoreCase) && (Team == -2 || B.Team == Team))
			{
				return B.Actor.Get();
			}
		}
		return nullptr;
	}

	/** "Barracks", "Barracks enemy", "Archery_Range 1": a name, then optionally a team. */
	AActor* BuildingFromArgs(UWorld* World, TArray<FString> Args)
	{
		int32 Team = 0;
		if (Args.Num() > 1 && (Args.Last().Equals(TEXT("enemy"), ESearchCase::IgnoreCase) || Args.Last() == TEXT("1") || Args.Last() == TEXT("0")))
		{
			Team = (Args.Last() == TEXT("0")) ? 0 : 1;
			Args.Pop();
		}
		return BuildingNamed(World, FString::Join(Args, TEXT(" ")), Team);
	}

	FAutoConsoleCommandWithWorldAndArgs CmdStartMatch(TEXT("vl.StartMatch"), TEXT("vl.StartMatch [0|1|2]: start the match here now (easy / normal / hard), skipping the menus"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UVLBattle* Battle = UVLBattle::Get(World))
			{
				Battle->StartMatch(Args.Num() ? FCString::Atoi(*Args[0]) : 1);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdBattle(TEXT("vl.Battle"), TEXT("log the battle: each side's stock, troops, buildings and the commanders"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (const UVLBattle* Battle = UVLBattle::Get(World))
			{
				Battle->LogStatus();
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdGive(TEXT("vl.Give"), TEXT("vl.Give gold|food N [enemy]: resources for a side (past its stores)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UVLBattle* Battle = UVLBattle::Get(World); Battle && Args.Num() >= 2)
			{
				const int32 Team = Args.Num() > 2 ? 1 : 0;
				Battle->AddStock(Team, Args[0].StartsWith(TEXT("g"), ESearchCase::IgnoreCase) ? EVLRes::Gold : EVLRes::Food, FCString::Atoi(*Args[1]), true);
				UE_LOG(LogSovereignRealms, Log, TEXT("give: team %d now has %d gold %d food"), Team, Battle->GetStock(Team, EVLRes::Gold), Battle->GetStock(Team, EVLRes::Food));
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdTestWorld(TEXT("vl.TestWorld"), TEXT("vl.TestWorld [0|1|2]: both sides at their most on this map, as New Game > Test World (starts the match if none is on)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UVLBattle* Battle = UVLBattle::Get(World))
			{
				Battle->StartMatch(Args.Num() > 0 ? FCString::Atoi(*Args[0]) : Battle->GetDifficulty());
				Battle->SetupTestWorld();
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdCohesion(TEXT("vl.Cohesion"), TEXT("vl.Cohesion: log each platoon's members, its spread, who is apart on purpose and who is on its way to the platoon's fight"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (const UVLBattle* Battle = UVLBattle::Get(World))
			{
				Battle->LogCohesion();
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSpyCooldown(TEXT("vl.SpyCooldown"), TEXT("vl.SpyCooldown [seconds] [enemy]: log (or set) the wait before a kingdom may train its next Spy, and why it could not train one now"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UVLBattle* Battle = UVLBattle::Get(World))
			{
				const int32 Team = Args.Contains(TEXT("enemy")) ? 1 : 0;
				if (Args.Num() > 0 && Args[0] != TEXT("enemy"))
				{
					Battle->SetSpyCooldown(Team, FCString::Atof(*Args[0]));
				}
				int32 Queued = 0;
				const int32 Alive = Battle->GetSpyCount(Team, &Queued);
				const FString Why = Battle->SpyRefusal(Team);
				UE_LOG(LogSovereignRealms, Log, TEXT("vl.SpyCooldown %s: %.1f s left, spies alive=%d queued=%d, castle level %d: %s"), Team == 1 ? TEXT("enemy") : TEXT("player"),
					Battle->GetSpyCooldown(Team), Alive, Queued, Battle->GetCastleLevel(Team), Why.IsEmpty() ? TEXT("may train one") : *Why);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSetTeam(TEXT("vl.SetTeam"), TEXT("vl.SetTeam <building name> 0|1|neutral: give a building of the level to a side"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLBattle* Battle = UVLBattle::Get(World);
			if (!Battle || Args.Num() < 2)
			{
				return;
			}
			TArray<FString> Words(Args);
			const FString Team = Words.Pop();
			const FName Tag(*(TEXT("Name:") + FString::Join(Words, TEXT(" ")).Replace(TEXT("_"), TEXT(" "))));
			for (TActorIterator<AActor> It(World); It; ++It)
			{
				if (It->ActorHasTag(Tag))
				{
					It->Tags.RemoveAll([](const FName& T) { return T.ToString().StartsWith(TEXT("Team:")); });
					It->Tags.Add(*(TEXT("Team:") + (Team.IsNumeric() ? Team : FString(TEXT("Neutral")))));
					Battle->RegisterBuilding(*It);
					UE_LOG(LogSovereignRealms, Log, TEXT("%s is now team %s"), *It->GetName(), *Team);
					return;
				}
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdTestBase(TEXT("vl.TestBase"), TEXT("vl.TestBase [DX DY] [team]: an enemy base, copies of the level's buildings mirrored and moved (default 0 4500: L_Flatlands)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UVLBattle* Battle = UVLBattle::Get(World))
			{
				const FVector Offset(Args.Num() > 0 ? FCString::Atof(*Args[0]) : 0.f, Args.Num() > 1 ? FCString::Atof(*Args[1]) : 4500.f, 0.f);
				Battle->SpawnTestBase(Offset, Args.Num() > 2 ? FCString::Atoi(*Args[2]) : 1);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdDamage(TEXT("vl.Damage"), TEXT("vl.Damage <building name> [enemy] Amount: hurt a building (as a blow from the other side)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLBattle* Battle = UVLBattle::Get(World);
			if (!Battle || Args.Num() < 2)
			{
				return;
			}
			TArray<FString> Words(Args);
			const float Amount = FCString::Atof(*Words.Pop());
			AActor* B = BuildingFromArgs(World, Words);
			if (B)
			{
				const float Done = Battle->Damage(B, Amount, nullptr, 1 - Battle->TeamOf(B));
				const FVLBuildingState* S = Battle->FindBuilding(B);
				UE_LOG(LogSovereignRealms, Log, TEXT("damage: %s takes %.0f, %.0f left"), *S->Name, Done, S->Health);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdUpgrade(TEXT("vl.Upgrade"), TEXT("vl.Upgrade <building name> [enemy]: raise it a level (paid, in its time)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLBattle* Battle = UVLBattle::Get(World);
			if (Battle && Args.Num() > 0)
			{
				AActor* B = BuildingFromArgs(World, Args);
				FVLCost Cost;
				const FString Why = Battle->UpgradeRefusal(B, &Cost);
				const bool bOk = B && Battle->Upgrade(B);
				UE_LOG(LogSovereignRealms, Log, TEXT("upgrade %s: %s"), B ? *B->GetName() : TEXT("(no such building)"), bOk ? TEXT("started") : *Why);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdTrainTeam(TEXT("vl.TrainAt"), TEXT("vl.TrainAt <building name> [enemy] [count]: queue troops there with the rules (price, housing)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLBattle* Battle = UVLBattle::Get(World);
			if (!Battle || Args.Num() == 0)
			{
				return;
			}
			TArray<FString> Words(Args);
			int32 Count = 1;
			if (Words.Num() > 1 && Words.Last().IsNumeric() && Words.Last() != TEXT("0") && Words.Last() != TEXT("1"))
			{
				Count = FCString::Atoi(*Words.Pop());
			}
			// a kind by name, for the castle's Builders: vl.TrainAt Castle Builder [enemy] [n]
			FString Kind;
			if (const int32 K = Words.IndexOfByPredicate([](const FString& W) { return W.Equals(TEXT("Builder"), ESearchCase::IgnoreCase); }); K != INDEX_NONE)
			{
				Kind = TEXT("Builder");
				Words.RemoveAt(K);
			}
			AActor* B = BuildingFromArgs(World, Words);
			const int32 N = B ? Battle->Train(B, Count, false, Kind) : 0;
			UE_LOG(LogSovereignRealms, Log, TEXT("train at %s: %d queued%s"), B ? *B->GetName() : TEXT("(no such building)"), N, N < Count && B ? *(TEXT(" (") + Battle->TrainRefusal(B, Kind) + TEXT(")")) : TEXT(""));
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdSpawnTeam(TEXT("vl.SpawnTeam"), TEXT("vl.SpawnTeam Swordsman|Archer 0|1 X Y [count]: troops of a side on the ground there, with no training"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLBattle* Battle = UVLBattle::Get(World);
			UVLGrid* Grid = UVLGrid::Get(World);
			if (!Battle || Args.Num() < 4)
			{
				return;
			}
			const int32 Count = Args.Num() > 4 ? FMath::Clamp(FCString::Atoi(*Args[4]), 1, 40) : 1;
			for (int32 i = 0; i < Count; ++i)
			{
				FVector P(FCString::Atof(*Args[2]) + (i % 5) * 130.f, FCString::Atof(*Args[3]) + (i / 5) * 130.f, 0.f);
				if (Grid && Grid->EnsureBuilt())
				{
					const int32 Node = Grid->NearestNode(FVector(P.X, P.Y, 100000.f), 20, Grid->MainRegion());
					if (Node != INDEX_NONE)
					{
						P = Grid->NodePos(Node);
					}
				}
				Battle->SpawnTroop(Args[0], FCString::Atoi(*Args[1]), P);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdAttackAt(TEXT("vl.AttackAt"), TEXT("vl.AttackAt <who> <building name> [enemy|0]: the player's units (all | troops | archers | swordsmen | selection | a name) attack that building (default: the enemy's)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLBattle* Battle = UVLBattle::Get(World);
			UVLCommand* Command = UVLCommand::Get(World);
			if (!Battle || !Command || Args.Num() < 2)
			{
				return;
			}
			TArray<FString> Words(Args);
			const FString Who = Words[0];
			Words.RemoveAt(0);
			int32 Team = 1;
			if (Words.Num() > 1 && (Words.Last() == TEXT("0") || Words.Last().Equals(TEXT("enemy"), ESearchCase::IgnoreCase)))
			{
				Team = Words.Pop() == TEXT("0") ? 0 : 1;
			}
			AActor* B = BuildingNamed(World, FString::Join(Words, TEXT(" ")), Team);
			TArray<AVLKing*> Units;
			if (Who.Equals(TEXT("selection"), ESearchCase::IgnoreCase))
			{
				Command->GetSelection(Units);
			}
			else
			{
				for (TActorIterator<AVLKing> It(World); It; ++It)
				{
					if (It->IsAlive() && It->Team == 0 && (Who.Equals(TEXT("all"), ESearchCase::IgnoreCase) || (Who.Equals(TEXT("troops"), ESearchCase::IgnoreCase) && It->IsTroop())
						|| (Who.Equals(TEXT("archers"), ESearchCase::IgnoreCase) && It->IsRanged()) || (Who.Equals(TEXT("swordsmen"), ESearchCase::IgnoreCase) && It->KindId() == EVLUnitKind::Swordsman)
						|| It->GetDisplayName().Equals(Who.Replace(TEXT("_"), TEXT(" ")), ESearchCase::IgnoreCase)))
					{
						Units.Add(*It);
					}
				}
			}
			const int32 N = B ? Command->OrderAttack(Units, B, false) : 0;
			UE_LOG(LogSovereignRealms, Log, TEXT("attack at %s: %d of %d unit(s) ordered"), B ? *B->GetName() : TEXT("(no such building)"), N, Units.Num());
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdAIvsAI(TEXT("vl.AIvsAI"), TEXT("vl.AIvsAI 0|1 [0|1|2]: a commander for the player's side too (balance tests), at the match's difficulty or the one given"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			if (UVLBattle* Battle = UVLBattle::Get(World))
			{
				Battle->SetPlayerAI(Args.Num() == 0 || FCString::Atoi(*Args[0]) != 0, Args.Num() > 1 ? FCString::Atoi(*Args[1]) : -1);
			}
		}));

	FAutoConsoleCommandWithWorldAndArgs CmdKill(TEXT("vl.Kill"), TEXT("vl.Kill <unit name> | castle [enemy|player]: a unit dies / a castle falls (vl.Kill castle enemy: victory)"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
		{
			UVLBattle* Battle = UVLBattle::Get(World);
			if (!Battle || Args.Num() == 0)
			{
				return;
			}
			if (Args[0].Equals(TEXT("castle"), ESearchCase::IgnoreCase))
			{
				const int32 Team = (Args.Num() > 1 && Args[1].StartsWith(TEXT("p"), ESearchCase::IgnoreCase)) ? 0 : 1;
				if (AActor* C = Battle->GetCastle(Team))
				{
					Battle->Damage(C, 1e7f, nullptr, 1 - Team);
				}
				return;
			}
			const FString Name = FString::Join(Args, TEXT(" ")).Replace(TEXT("_"), TEXT(" "));
			for (TActorIterator<AVLKing> It(World); It; ++It)
			{
				if (It->IsAlive() && (It->GetDisplayName().Equals(Name, ESearchCase::IgnoreCase) || (Name.Equals(TEXT("king"), ESearchCase::IgnoreCase) && !It->IsTroop())))
				{
					Battle->Damage(*It, 1e6f, nullptr, 1 - It->Team);
					return;
				}
			}
		}));
}
