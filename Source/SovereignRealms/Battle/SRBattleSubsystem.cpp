// Copyright Sovereign Realms.

#include "Battle/SRBattleSubsystem.h"
#include "Battle/SRGridSubsystem.h"
#include "Battle/SRAISubsystem.h"
#include "Battle/SRPlatoonSubsystem.h"
#include "Battle/SRFormation.h"
#include "Buildings/SRBuilding.h"
#include "Common/SRAudioSubsystem.h"
#include "Units/SRUnit.h"
#include "Units/SRProjectile.h"
#include "Battle/SROrderMarker.h"
#include "Battle/SREconomySubsystem.h"
#include "Buildings/SRBuilding.h"
#include "Player/SRCameraPawn.h"
#include "Common/SRFeelSettings.h"
#include "SovereignRealms.h"
#include "Engine/World.h"
#include "Engine/Engine.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/DirectionalLight.h"
#include "Components/StaticMeshComponent.h"
#include "Materials/Material.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UnrealClient.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "Camera/PlayerCameraManager.h"
#include "Misc/PackageName.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "HAL/FileManager.h"

namespace
{
	/** A sprite asset made by Tools/import_character_sprites.py / build_visual_materials.py. Missing = the pipeline has not been run. */
	template <typename T>
	T* LoadSpriteAsset(const TCHAR* ObjectPath)
	{
		T* Asset = LoadObject<T>(nullptr, ObjectPath);
		if (!Asset)
		{
			UE_LOG(LogSovereign, Error, TEXT("Missing sprite asset %s: run Tools/import_character_sprites.py and Tools/build_visual_materials.py (see Docs/VISUAL_CONTRACT.md)."), ObjectPath);
		}
		return Asset;
	}

	UMaterialInterface* OrDefault(UMaterialInterface* Material)
	{
		return Material ? Material : UMaterial::GetDefaultMaterial(MD_Surface);
	}

	/** Loads a project material if the visual pass has created it, otherwise the engine fallback. */
	UMaterialInterface* LoadContractMaterial(const TCHAR* PackagePath, const TCHAR* ObjectPath, bool& bOutIsFallback)
	{
		bOutIsFallback = true;
		if (FPackageName::DoesPackageExist(PackagePath))
		{
			if (UMaterialInterface* Mat = LoadObject<UMaterialInterface>(nullptr, ObjectPath))
			{
				bOutIsFallback = false;
				return Mat;
			}
		}
		return LoadObject<UMaterialInterface>(nullptr, TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	}
}

USRBattleSubsystem* USRBattleSubsystem::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<USRBattleSubsystem>() : nullptr;
}

bool USRBattleSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

TStatId USRBattleSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(USRBattleSubsystem, STATGROUP_Tickables);
}

void USRBattleSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	// Troop sprites: see Docs/VISUAL_CONTRACT.md. One dynamic instance per troop type (not per unit), so the
	// Sovereign Feel > Visuals > Sprites look values can be tuned live; per-unit values are custom primitive data.
	UnitCardMesh = LoadSpriteAsset<UStaticMesh>(TEXT("/Game/SR/Characters/SM_UnitCard.SM_UnitCard"));
	ArrowCardMesh = LoadSpriteAsset<UStaticMesh>(TEXT("/Game/SR/Characters/SM_ArrowCard.SM_ArrowCard"));
	SpriteMaterials[0] = UMaterialInstanceDynamic::Create(OrDefault(LoadSpriteAsset<UMaterialInterface>(TEXT("/Game/SR/Materials/MI_UnitSprite_Shieldbearer.MI_UnitSprite_Shieldbearer"))), this);
	SpriteMaterials[1] = UMaterialInstanceDynamic::Create(OrDefault(LoadSpriteAsset<UMaterialInterface>(TEXT("/Game/SR/Materials/MI_UnitSprite_Archer.MI_UnitSprite_Archer"))), this);
	SpriteShadowMaterials[0] = OrDefault(LoadSpriteAsset<UMaterialInterface>(TEXT("/Game/SR/Materials/MI_UnitSpriteShadow_Shieldbearer.MI_UnitSpriteShadow_Shieldbearer")));
	SpriteShadowMaterials[1] = OrDefault(LoadSpriteAsset<UMaterialInterface>(TEXT("/Game/SR/Materials/MI_UnitSpriteShadow_Archer.MI_UnitSpriteShadow_Archer")));
	WorkerMaterials[0] = UMaterialInstanceDynamic::Create(OrDefault(LoadSpriteAsset<UMaterialInterface>(TEXT("/Game/SR/Materials/MI_UnitSprite_Miner.MI_UnitSprite_Miner"))), this);
	WorkerMaterials[1] = UMaterialInstanceDynamic::Create(OrDefault(LoadSpriteAsset<UMaterialInterface>(TEXT("/Game/SR/Materials/MI_UnitSprite_Farmer.MI_UnitSprite_Farmer"))), this);
	WorkerShadowMaterials[0] = OrDefault(LoadSpriteAsset<UMaterialInterface>(TEXT("/Game/SR/Materials/MI_UnitSpriteShadow_Miner.MI_UnitSpriteShadow_Miner")));
	WorkerShadowMaterials[1] = OrDefault(LoadSpriteAsset<UMaterialInterface>(TEXT("/Game/SR/Materials/MI_UnitSpriteShadow_Farmer.MI_UnitSpriteShadow_Farmer")));
	ArrowMaterial = UMaterialInstanceDynamic::Create(OrDefault(LoadSpriteAsset<UMaterialInterface>(TEXT("/Game/SR/Materials/MI_ArrowSprite.MI_ArrowSprite"))), this);
	ArrowShadowMaterial = OrDefault(LoadSpriteAsset<UMaterialInterface>(TEXT("/Game/SR/Materials/MI_ArrowShadow.MI_ArrowShadow")));
	BlobMaterial = LoadSpriteAsset<UMaterialInterface>(TEXT("/Game/SR/Materials/M_UnitBlob.M_UnitBlob"));

	bool bFallback = true;
	RingMaterial = LoadContractMaterial(TEXT("/Game/SR/Materials/M_SelectionRing"), TEXT("/Game/SR/Materials/M_SelectionRing.M_SelectionRing"), bFallback);
	CubeMesh = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
	GreyboxMaterial = LoadContractMaterial(TEXT("/Game/SR/Materials/M_UnitGreybox"), TEXT("/Game/SR/Materials/M_UnitGreybox.M_UnitGreybox"), bFallback);
}

UMaterialInterface* USRBattleSubsystem::GetSpriteMaterial(ESRUnitType Type) const
{
	return SpriteMaterials[Type == ESRUnitType::Archer ? 1 : 0];
}

UMaterialInterface* USRBattleSubsystem::GetSpriteShadowMaterial(ESRUnitType Type) const
{
	return SpriteShadowMaterials[Type == ESRUnitType::Archer ? 1 : 0];
}

// ----------------------------------------------------------- sprite view

void USRBattleSubsystem::UpdateSpriteView()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	UWorld* World = GetWorld();

	// The camera pawn has already ticked this frame (it ticks with the actors, this subsystem after them),
	// so its rotation is the one the frame will be rendered with.
	FRotator ViewRot(FMath::Lerp(F.PitchZoomedIn, F.PitchZoomedOut, F.ZoomDefault), F.CameraYaw, 0.f);
	const APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
	if (const ASRCameraPawn* Camera = PC ? Cast<ASRCameraPawn>(PC->GetPawn()) : nullptr)
	{
		ViewRot = Camera->GetViewRotation();
	}
	else if (PC && PC->PlayerCameraManager)
	{
		ViewRot = PC->PlayerCameraManager->GetCameraRotation();
	}
	const FRotationMatrix ViewAxes(ViewRot);
	SpriteView.CardRotation = ViewRot.Quaternion();
	SpriteView.ViewForward = ViewAxes.GetUnitAxis(EAxis::X);
	SpriteView.ViewUp = ViewAxes.GetUnitAxis(EAxis::Z);
	SpriteView.ViewYaw = ViewRot.Yaw;
	const float PitchDown = FMath::Clamp(-ViewRot.Pitch, 5.f, 80.f);
	SpriteView.HeightScale = FMath::Cos(FMath::DegreesToRadians(SRSprite::RenderElevationDeg)) / FMath::Cos(FMath::DegreesToRadians(PitchDown));

	// The sun: the level's directional light, or the contract's direction if there is none.
	if (!bSunSearched && World)
	{
		bSunSearched = true;
		if (TActorIterator<ADirectionalLight> It(World); It) { Sun = *It; }
	}
	FVector SunDir = Sun.IsValid() ? Sun->GetActorForwardVector() : FVector(0.22f, 0.81f, -0.54f);
	FVector2D Flat(SunDir.X, SunDir.Y);
	if (!Flat.Normalize()) { Flat = FVector2D(0.f, 1.f); }
	const float Elevation = FMath::DegreesToRadians(FMath::Clamp(FMath::RadiansToDegrees(FMath::Asin(FMath::Clamp(-SunDir.Z, -1.f, 1.f))), 12.f, 80.f));
	SpriteView.SunDir = FVector(Flat.X * FMath::Cos(Elevation), Flat.Y * FMath::Cos(Elevation), -FMath::Sin(Elevation));
	SpriteView.SunYaw = FMath::RadiansToDegrees(FMath::Atan2(Flat.Y, Flat.X));

	// Shadow card. The exact caster is the frame on a card facing the sun (the sheets were rendered from 30 degrees,
	// the sun stands at 33, so the sun sees almost what the sheet's camera saw). Sliding every point of that card
	// along the light does not change the shadow it throws, so the card can lie in any plane through the feet:
	// here one leaning Lean degrees from upright, away from the sun. Card axes: Y = the sun-viewer's right,
	// Z = "sprite up" slid onto that plane (longer than 1, hence the scale).
	const float Lean = FMath::DegreesToRadians(FMath::Clamp(F.SpriteShadowLean, 0.f, 88.f));
	const float Slide = FMath::Tan(Lean - Elevation);
	const FVector FlatDir(Flat.X, Flat.Y, 0.f);
	const FVector Up = FlatDir * (FMath::Sin(Elevation) + Slide * FMath::Cos(Elevation))
		+ FVector::UpVector * (FMath::Cos(Elevation) - Slide * FMath::Sin(Elevation));
	const FVector AxisY(-Flat.Y, Flat.X, 0.f);
	const FVector AxisZ = Up.GetSafeNormal();
	const FVector AxisX = FVector::CrossProduct(AxisY, AxisZ);
	SpriteView.ShadowRotation = FMatrix(AxisX, AxisY, AxisZ, FVector::ZeroVector).ToQuat();
	SpriteView.ShadowScale = FVector(1.f, 1.f, Up.Size());
}

void USRBattleSubsystem::UpdateSpriteLook()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const FVector4 Look(F.SpriteRelight, F.SpriteBakedLight, F.SpriteNormalStrength, F.SpriteEdgeSoftness);
	if (Look.Equals(AppliedSpriteLook, 0.0005f) && F.HitFlashColor.Equals(AppliedFlashColor, 0.0005f)) { return; }
	AppliedSpriteLook = Look;
	AppliedFlashColor = F.HitFlashColor;
	for (UMaterialInstanceDynamic* MID : { SpriteMaterials[0].Get(), SpriteMaterials[1].Get(), WorkerMaterials[0].Get(), WorkerMaterials[1].Get(), ArrowMaterial.Get() })
	{
		if (!MID) { continue; }
		MID->SetScalarParameterValue(TEXT("Relight"), F.SpriteRelight);
		MID->SetScalarParameterValue(TEXT("BakedLight"), F.SpriteBakedLight);
		MID->SetScalarParameterValue(TEXT("EdgeSoftness"), F.SpriteEdgeSoftness);
		MID->SetVectorParameterValue(TEXT("HitFlashColor"), F.HitFlashColor);
		if (MID != ArrowMaterial) { MID->SetScalarParameterValue(TEXT("NormalStrength"), F.SpriteNormalStrength); }
	}
}

// ------------------------------------------------------------------ frame

void USRBattleSubsystem::Tick(float DeltaTime)
{
	Super::Tick(DeltaTime);
	PollCommandInbox(DeltaTime);
	UpdateSpriteView();
	UpdateSpriteLook();

	if (!bBattleStarted) { return; }

	if (bSimPaused)
	{
		// Menus: hold everything where it stands, but keep the sprites facing the (still moving) camera.
		for (ASRUnit* Unit : Units) { if (Unit) { Unit->StepVisual(0.f); } }
		for (ASRUnit* Corpse : Corpses) { if (Corpse) { Corpse->StepVisual(0.f); } }
		return;
	}

	if (FreezeFramesLeft > 0)
	{
		// Debug capture (sr.ShotOn): hold the battle on the frame of the event until the image has settled
		// (temporal upscaling, Lumen, depth of field all need a few frames after the camera jump), then shoot.
		--FreezeFramesLeft;
		for (ASRUnit* Unit : Units) { if (Unit) { Unit->StepVisual(0.f); } }
		for (ASRUnit* Corpse : Corpses) { if (Corpse) { Corpse->StepVisual(0.f); } }
		if (bShotPending && FreezeFramesLeft <= 4)
		{
			bShotPending = false;
			const FString Path = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir() / TEXT("Screenshots/SR") / (ArmedShotName + TEXT(".png")));
			FScreenshotRequest::RequestScreenshot(Path, true, false);
			const ASRUnit* Unit = ArmedUnit.Get();
			UE_LOG(LogSovereign, Log, TEXT("sr.ShotOn -> %s  (%s shows cell anim=%d frame=%d facing=%d)"), *Path,
				Unit ? *Unit->GetLabel() : TEXT("?"), Unit ? int32(Unit->GetSpriteAnim()) : -1, Unit ? Unit->GetSpriteFrame() : -1, Unit ? Unit->GetSpriteFacing() : -1);
		}
		return;
	}

	// Sub-step long frames (a hitch, or the game sped up for balance tests) so nothing teleports through anything.
	const float Total = FMath::Min(DeltaTime, 0.25f);
	const int32 Steps = FMath::Clamp(FMath::CeilToInt(Total / 0.034f), 1, 8);
	for (int32 k = 0; k < Steps; ++k) { StepFrame(Total / Steps); }
	if (USRGridSubsystem* Grid = USRGridSubsystem::Get(this); Grid && USRFeelSettings::Get().bDebugDrawPaths) { Grid->DebugDraw(); }
}

void USRBattleSubsystem::StepFrame(float Dt)
{
	BattleClock += Dt;

	// The commanders (enemy, and the player's side in AI-vs-AI tests) and the platoons decide before anyone moves.
	if (USRAISubsystem* AI = USRAISubsystem::Get(this)) { AI->Step(Dt); }
	if (USRPlatoonSubsystem* Platoons = USRPlatoonSubsystem::Get(this)) { Platoons->Step(Dt); }

	// 1) think + move  2) push overlapping bodies apart  3) pose and place the actors
	for (int32 i = 0; i < Units.Num(); ++i)
	{
		if (Units[i]) { Units[i]->StepSim(Dt); }
	}
	ResolveOverlaps(Dt);
	ResolveOverlaps(Dt); // second pass settles three-body pile-ups

	// Anything killed this frame leaves the combat list now and finishes its death as a corpse.
	for (int32 i = Units.Num() - 1; i >= 0; --i)
	{
		if (!Units[i] || !Units[i]->IsAlive())
		{
			if (Units[i]) { Corpses.Add(Units[i]); }
			Units.RemoveAt(i);
		}
	}

	for (ASRUnit* Unit : Units) { Unit->StepVisual(Dt); }

	for (int32 i = Corpses.Num() - 1; i >= 0; --i)
	{
		ASRUnit* Corpse = Corpses[i];
		if (Corpse) { Corpse->StepVisual(Dt); }
		if (!Corpse || Corpse->IsCorpseExpired())
		{
			if (Corpse) { Corpse->Destroy(); }
			Corpses.RemoveAt(i);
		}
	}

	// Buildings: production, recruit queues, payout popups. Stepped here so they freeze and reset with the battle.
	if (USREconomySubsystem* Economy = USREconomySubsystem::Get(this)) { Economy->Step(Dt); }

	CheckResult();
	if (Result != ESRBattleResult::Ongoing) { TimeSinceResult += Dt; }
}

void USRBattleSubsystem::ResolveOverlaps(float DeltaTime)
{
	const float Fraction = FMath::Min(1.f, USRFeelSettings::Get().OverlapResolveRate * DeltaTime * 0.5f);

	for (int32 i = 0; i < Units.Num(); ++i)
	{
		ASRUnit* A = Units[i];
		if (!A || !A->IsAlive()) { continue; }
		for (int32 j = i + 1; j < Units.Num(); ++j)
		{
			ASRUnit* B = Units[j];
			if (!B || !B->IsAlive()) { continue; }

			FVector2D Delta = B->GetPos2D() - A->GetPos2D();
			float Dist = Delta.Size();
			const float MinDist = A->GetRadius() + B->GetRadius();
			if (Dist >= MinDist) { continue; }
			if (Dist < 0.5f) { Delta = FVector2D(1.f, 0.f); Dist = 0.5f; }

			// Remove a fraction of the overlap per frame (soft, no popping), split by mass.
			const FVector2D Push = (Delta / Dist) * (MinDist - Dist) * Fraction;
			const float MassA = A->GetPushMass(), MassB = B->GetPushMass();
			FVector2D PushA = -Push * (MassB / (MassA + MassB));
			FVector2D PushB = Push * (MassA / (MassA + MassB));

			// A friend walking into a unit that is standing its ground should not carry it along:
			// the stander only steps sideways, and the walker absorbs the rest (then steers round).
			if (A->GetTeam() == B->GetTeam() && A->IsPlanted() != B->IsPlanted())
			{
				const bool bAStands = A->IsPlanted();
				const FVector2D TravelDir = (bAStands ? B : A)->GetVelocity2D().GetSafeNormal();
				FVector2D& StanderPush = bAStands ? PushA : PushB;
				FVector2D& WalkerPush = bAStands ? PushB : PushA;
				const FVector2D Carried = TravelDir * FMath::Max(FVector2D::DotProduct(StanderPush, TravelDir), 0.f);
				StanderPush -= Carried;
				WalkerPush -= Carried;
			}
			A->Nudge(PushA);
			B->Nudge(PushB);
		}
	}
}

void USRBattleSubsystem::NotifyBuildingDestroyed(ASRBuilding* Building)
{
	if (Building) { ++MatchStats.BuildingsLost[int32(Building->Team)]; }
	if (!Building || !Building->IsCastle() || Result != ESRBattleResult::Ongoing) { return; }
	Result = Building->Team == ESRTeam::Enemy ? ESRBattleResult::PlayerWon : ESRBattleResult::EnemyWon;
	TimeSinceResult = 0.f;
	UE_LOG(LogSovereign, Log, TEXT("BATTLE RESULT: %s after %.1fs (the %s castle fell)  (troops: player=%d enemy=%d)"),
		Result == ESRBattleResult::PlayerWon ? TEXT("PLAYER VICTORY") : TEXT("PLAYER DEFEAT"), BattleClock,
		Building->Team == ESRTeam::Enemy ? TEXT("enemy") : TEXT("player"), CountAlive(ESRTeam::Player), CountAlive(ESRTeam::Enemy));
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->Play2D(Result == ESRBattleResult::PlayerWon ? ESRSound::Victory : ESRSound::Defeat); }
}

void USRBattleSubsystem::CheckResult()
{
	if (Result != ESRBattleResult::Ongoing) { return; }
	// With kingdoms on the map the match is decided by the castles (NotifyBuildingDestroyed); a side that has lost its
	// castle and every troop is out too. Without castles (a bare test map) the last army standing wins.
	if (const USREconomySubsystem* Eco = USREconomySubsystem::Get(this))
	{
		const bool bPlayerCastle = Eco->GetCastle(ESRTeam::Player) != nullptr;
		const bool bEnemyCastle = Eco->GetCastle(ESRTeam::Enemy) != nullptr;
		if (bPlayerCastle || bEnemyCastle) { return; }
	}

	const int32 Players = CountAlive(ESRTeam::Player);
	const int32 Enemies = CountAlive(ESRTeam::Enemy);
	if (Players > 0 && Enemies > 0) { return; }

	Result = Enemies == 0 ? ESRBattleResult::PlayerWon : ESRBattleResult::EnemyWon;
	TimeSinceResult = 0.f;
	UE_LOG(LogSovereign, Log, TEXT("BATTLE RESULT: %s after %.1fs  (survivors: player=%d enemy=%d)"),
		Result == ESRBattleResult::PlayerWon ? TEXT("PLAYER VICTORY") : TEXT("PLAYER DEFEAT"), BattleClock, Players, Enemies);
}

// --------------------------------------------------------------- scenario

void USRBattleSubsystem::ResetBattle()
{
	UWorld* World = GetWorld();
	if (!World) { return; }

	for (ASRUnit* Unit : Units) { if (Unit) { Unit->Destroy(); } }
	for (ASRUnit* Corpse : Corpses) { if (Corpse) { Corpse->Destroy(); } }
	for (AActor* Obstacle : Obstacles) { if (Obstacle) { Obstacle->Destroy(); } }
	Units.Reset();
	Corpses.Reset();
	Obstacles.Reset();
	for (TActorIterator<ASRProjectile> It(World); It; ++It) { It->Destroy(); }
	for (TActorIterator<ASROrderMarker> It(World); It; ++It) { It->Destroy(); }

	bAutoBattle = false;
	MatchStats = FSRMatchStats();
	Result = ESRBattleResult::Ongoing;
	TimeSinceResult = 0.f;
	BattleClock = 0.f;
	FreezeFramesLeft = 0;
	bShotPending = false;
	ArmedEvent = ESRShotEvent::None;

	UpdateSpriteView(); // units pose themselves as they spawn
	UpdateSpriteLook();
	SpawnObstacles();
	SpawnScenario();
	if (USREconomySubsystem* Economy = USREconomySubsystem::Get(this)) { Economy->Reset(); }
	if (USRAISubsystem* AI = USRAISubsystem::Get(this)) { AI->Reset(); }
	if (USRPlatoonSubsystem* Platoons = USRPlatoonSubsystem::Get(this)) { Platoons->Reset(); }
	if (USRAudioSubsystem* Audio = USRAudioSubsystem::Get(this)) { Audio->StartLoops(); }
	bBattleStarted = true;

	UE_LOG(LogSovereign, Log, TEXT("BATTLE RESET: player=%d enemy=%d"), CountAlive(ESRTeam::Player), CountAlive(ESRTeam::Enemy));
}

ASRUnit* USRBattleSubsystem::SpawnUnit(ESRUnitType Type, ESRTeam Team, const FVector2D& Location, float Yaw, float SpawnDelay)
{
	UWorld* World = GetWorld();
	float GroundZ = 0.f;
	SampleGround(Location, 20000.f, GroundZ);

	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ASRUnit* Unit = World->SpawnActor<ASRUnit>(FVector(Location.X, Location.Y, GroundZ), FRotator(0.f, Yaw, 0.f), Params);
	if (Unit)
	{
		const FSRUnitStats& Stats = USRFeelSettings::Get().StatsFor(Type);
		const FString Label = FString::Printf(TEXT("%s-%s-%d"), Team == ESRTeam::Player ? TEXT("P") : TEXT("E"), *Stats.DisplayName, Units.Num());
		Unit->InitUnit(Type, Team, SpawnDelay, Label);
		Units.Add(Unit);
	}
	return Unit;
}

void USRBattleSubsystem::SpawnScenario()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	FRandomStream Rng(1337); // same layout every reset so fights are comparable while tuning

	const FVector2D ToEnemy = (F.EnemyStart - F.PlayerStart).GetSafeNormal();
	const FVector2D Fwd = ToEnemy.IsNearlyZero() ? FVector2D(1.f, 0.f) : ToEnemy;
	const FVector2D Right(-Fwd.Y, Fwd.X);
	const float PlayerYaw = FMath::RadiansToDegrees(FMath::Atan2(Fwd.Y, Fwd.X));

	// Player: tidy battle line, shields in front, archers behind.
	auto SpawnLine = [&](ESRUnitType Type, int32 Count, float Depth)
	{
		const float Spacing = F.StatsFor(Type).Radius * 2.f + F.FormationGap;
		for (int32 i = 0; i < Count; ++i)
		{
			const float Lateral = (i - (Count - 1) * 0.5f) * Spacing;
			SpawnUnit(Type, ESRTeam::Player, F.PlayerStart + Fwd * Depth + Right * Lateral, PlayerYaw, Rng.FRandRange(0.f, F.SpawnStagger));
		}
	};
	SpawnLine(ESRUnitType::Shieldbearer, F.PlayerShieldbearers, 70.f);
	SpawnLine(ESRUnitType::Archer, F.PlayerArchers, -90.f);

	// Enemy: a looser warband facing the player, melee toward the front.
	auto SpawnMob = [&](ESRUnitType Type, int32 Count, float Depth, float Spread)
	{
		for (int32 i = 0; i < Count; ++i)
		{
			const float Lateral = (i - (Count - 1) * 0.5f) * Spread + Rng.FRandRange(-45.f, 45.f);
			const float Jitter = Rng.FRandRange(-70.f, 70.f);
			SpawnUnit(Type, ESRTeam::Enemy, F.EnemyStart - Fwd * (Depth + Jitter) + Right * Lateral,
				PlayerYaw + 180.f + Rng.FRandRange(-25.f, 25.f), Rng.FRandRange(0.f, F.SpawnStagger));
		}
	};
	SpawnMob(ESRUnitType::Shieldbearer, F.EnemyShieldbearers, 90.f, 190.f);
	SpawnMob(ESRUnitType::Archer, F.EnemyArchers, -150.f, 240.f);
}

void USRBattleSubsystem::SpawnObstacles()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (!F.bSpawnGreyboxObstacles) { return; }

	struct FBlock { FVector2D Pos; FVector Size; float Yaw; };
	const FBlock Blocks[] = {
		{ FVector2D(150.f, -260.f),  FVector(230.f, 190.f, 150.f), 20.f },
		{ FVector2D(-250.f, 820.f),  FVector(300.f, 220.f, 210.f), -35.f },
		{ FVector2D(650.f, -900.f),  FVector(260.f, 260.f, 180.f), 50.f },
	};

	for (const FBlock& Block : Blocks)
	{
		float GroundZ = 0.f;
		SampleGround(Block.Pos, 20000.f, GroundZ);
		AStaticMeshActor* Actor = GetWorld()->SpawnActor<AStaticMeshActor>(
			FVector(Block.Pos.X, Block.Pos.Y, GroundZ + Block.Size.Z * 0.5f - 10.f), FRotator(0.f, Block.Yaw, 0.f));
		if (!Actor) { continue; }

		UStaticMeshComponent* Mesh = Actor->GetStaticMeshComponent();
		Mesh->SetMobility(EComponentMobility::Movable);
		Mesh->SetStaticMesh(CubeMesh);
		Mesh->SetWorldScale3D(Block.Size / 100.f);
		Mesh->SetCollisionProfileName(TEXT("BlockAll"));
		Mesh->SetCollisionObjectType(ECC_WorldStatic); // units and ground traces only look at WorldStatic
		UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(GreyboxMaterial, Mesh);
		MID->SetVectorParameterValue(TEXT("Color"), FLinearColor(0.33f, 0.31f, 0.28f));
		MID->SetVectorParameterValue(TEXT("TeamColor"), FLinearColor(0.33f, 0.31f, 0.28f));
		Mesh->SetMaterial(0, MID);
		Actor->Tags.Add(TEXT("SRGreyboxObstacle"));
		Obstacles.Add(Actor);
	}
}

void USRBattleSubsystem::SetAutoBattle(bool bEnabled)
{
	bAutoBattle = bEnabled;
	UE_LOG(LogSovereign, Log, TEXT("AUTOBATTLE %s"), bEnabled ? TEXT("ON") : TEXT("OFF"));
	if (!bEnabled) { return; }

	const FVector2D PlayerCentre = TeamCentroid(ESRTeam::Player);
	const FVector2D EnemyCentre = TeamCentroid(ESRTeam::Enemy);
	for (ASRUnit* Unit : Units)
	{
		if (Unit && Unit->IsAlive())
		{
			Unit->OrderAttackMove(Unit->GetTeam() == ESRTeam::Player ? EnemyCentre : PlayerCentre);
		}
	}
}

// ---------------------------------------------------------------- queries

ASRUnit* USRBattleSubsystem::FindNearestEnemy(const ASRUnit* For, float Range) const
{
	ASRUnit* Best = nullptr;
	float BestDistSq = Range * Range;
	const FVector2D Pos = For->GetPos2D();
	for (ASRUnit* Other : Units)
	{
		if (!Other || !Other->IsActive() || Other->GetTeam() == For->GetTeam()) { continue; }
		const float DistSq = FVector2D::DistSquared(Pos, Other->GetPos2D());
		if (DistSq < BestDistSq)
		{
			BestDistSq = DistSq;
			Best = Other;
		}
	}
	return Best;
}

ASRUnit* USRBattleSubsystem::PickUnit(const FVector& RayOrigin, const FVector& RayDir, float Padding) const
{
	ASRUnit* Best = nullptr;
	float BestAlong = TNumericLimits<float>::Max();
	const FVector RayEnd = RayOrigin + RayDir * 200000.f;

	for (ASRUnit* Unit : Units)
	{
		if (!Unit || !Unit->IsActive()) { continue; }
		// Treat the unit as a fat capsule from feet to head, standing where its sprite is drawn.
		FVector Feet, Head;
		Unit->GetPickSegment(Feet, Head);
		FVector OnRay, OnUnit;
		FMath::SegmentDistToSegmentSafe(RayOrigin, RayEnd, Feet, Head, OnRay, OnUnit);
		if (FVector::DistSquared(OnRay, OnUnit) <= FMath::Square(Unit->GetRadius() + Padding))
		{
			const float Along = FVector::DotProduct(OnRay - RayOrigin, RayDir);
			if (Along < BestAlong)
			{
				BestAlong = Along;
				Best = Unit;
			}
		}
	}
	return Best;
}

void USRBattleSubsystem::IgnoreBuildings(FCollisionQueryParams& Params) const
{
	if (const USREconomySubsystem* Economy = USREconomySubsystem::Get(this))
	{
		for (const ASRBuilding* Building : Economy->GetBuildings())
		{
			if (Building) { Params.AddIgnoredActor(Building); }
		}
	}
}

bool USRBattleSubsystem::SampleGround(const FVector2D& XY, float RefZ, float& OutZ) const
{
	const UWorld* World = GetWorld();
	if (!World) { return false; }

	FHitResult Hit;
	const FVector Start(XY.X, XY.Y, RefZ + 400.f);
	const FVector End(XY.X, XY.Y, RefZ - 50000.f);
	FCollisionQueryParams Params(SCENE_QUERY_STAT(SRGround), false);
	IgnoreBuildings(Params); // a building's blocking box is a wall, never ground: the camera and the cursor look through it
	if (World->LineTraceSingleByObjectType(Hit, Start, End, FCollisionObjectQueryParams(ECC_WorldStatic), Params))
	{
		OutZ = Hit.ImpactPoint.Z;
		return true;
	}
	return false;
}

FVector USRBattleSubsystem::RayToGround(const FVector& RayOrigin, const FVector& RayDir) const
{
	FHitResult Hit;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(SRCursor), false);
	IgnoreBuildings(Params);
	if (GetWorld()->LineTraceSingleByObjectType(Hit, RayOrigin, RayOrigin + RayDir * 200000.f, FCollisionObjectQueryParams(ECC_WorldStatic), Params))
	{
		return Hit.ImpactPoint;
	}
	if (FMath::Abs(RayDir.Z) > KINDA_SMALL_NUMBER)
	{
		return RayOrigin + RayDir * (-RayOrigin.Z / RayDir.Z);
	}
	return RayOrigin;
}

bool USRBattleSubsystem::IsPathBlocked(const FVector& From, const FVector& To) const
{
	// Horizontal ray just above the tallest ledge a unit may step up: anything it hits is a wall, not a step.
	const float Height = USRFeelSettings::Get().StepHeight + 5.f;
	FHitResult Hit;
	const FCollisionQueryParams Params(SCENE_QUERY_STAT(SRPath), false);
	return GetWorld()->LineTraceSingleByObjectType(Hit, FVector(From.X, From.Y, From.Z + Height), FVector(To.X, To.Y, From.Z + Height),
		FCollisionObjectQueryParams(ECC_WorldStatic), Params);
}

FVector2D USRBattleSubsystem::ClipToReachable(const FVector& From, const FVector2D& To, float Clearance) const
{
	const float Height = USRFeelSettings::Get().StepHeight + 5.f;
	const FVector Start(From.X, From.Y, From.Z + Height);
	const FVector End(To.X, To.Y, From.Z + Height);
	FHitResult Hit;
	const FCollisionQueryParams Params(SCENE_QUERY_STAT(SRClip), false);
	if (!GetWorld()->LineTraceSingleByObjectType(Hit, Start, End, FCollisionObjectQueryParams(ECC_WorldStatic), Params))
	{
		return To;
	}
	const FVector Dir = (End - Start).GetSafeNormal();
	const FVector Clipped = Start + Dir * FMath::Max(Hit.Distance - Clearance, 0.f);
	return FVector2D(Clipped.X, Clipped.Y);
}

void USRBattleSubsystem::NotifyUnitDied(ASRUnit* Unit, const ASRUnit* Killer)
{
	UE_LOG(LogSovereign, Log, TEXT("DEATH %s  killed by %s  (remaining: player=%d enemy=%d)"),
		*Unit->GetLabel(), Killer ? *Killer->GetLabel() : TEXT("?"), CountAlive(ESRTeam::Player), CountAlive(ESRTeam::Enemy));
	++MatchStats.TroopsLost[int32(Unit->GetTeam())];
	OnShotEvent(ESRShotEvent::Death, Unit);
}

void USRBattleSubsystem::ArmShot(ESRShotEvent Event, const FString& Name, int32 UnitType, int32 Team)
{
	ArmedEvent = Event;
	ArmedShotName = Name;
	ArmedUnitType = UnitType;
	ArmedTeam = Team;
}

void USRBattleSubsystem::OnShotEvent(ESRShotEvent Event, ASRUnit* Unit)
{
	if (Event != ArmedEvent || !Unit) { return; }
	if (ArmedUnitType >= 0 && int32(Unit->GetUnitType()) != ArmedUnitType) { return; }
	if (ArmedTeam >= 0 && int32(Unit->GetTeam()) != ArmedTeam) { return; }

	ArmedEvent = ESRShotEvent::None;
	ArmedUnit = Unit;
	FreezeFramesLeft = 24;
	bShotPending = true;
	UE_LOG(LogSovereign, Log, TEXT("sr.ShotOn: %s at (%.0f, %.0f), freezing"), *Unit->GetLabel(), Unit->GetSimPos().X, Unit->GetSimPos().Y);
	const APlayerController* PC = GetWorld()->GetFirstPlayerController();
	if (ASRCameraPawn* Camera = PC ? Cast<ASRCameraPawn>(PC->GetPawn()) : nullptr)
	{
		Camera->FocusOn(Unit->GetPos2D(), true);
	}
}

void USRBattleSubsystem::AddCameraTrauma(const FVector& WorldLocation, float Amount) const
{
	const APlayerController* PC = GetWorld()->GetFirstPlayerController();
	if (ASRCameraPawn* Camera = PC ? Cast<ASRCameraPawn>(PC->GetPawn()) : nullptr)
	{
		// Things happening far from where the player is looking should barely register.
		const float Dist = FVector::Dist2D(WorldLocation, Camera->GetFocusPoint());
		const float Falloff = 1.f - FMath::Clamp(Dist / (Camera->GetZoomDistance() * 0.9f), 0.f, 1.f);
		Camera->AddTrauma(Amount * Falloff);
	}
}

FLinearColor USRBattleSubsystem::TeamColor(ESRTeam Team) const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	return Team == ESRTeam::Player ? F.PlayerTeamColor : F.EnemyTeamColor;
}

FVector2D USRBattleSubsystem::TeamCentroid(ESRTeam Team) const
{
	FVector2D Sum = FVector2D::ZeroVector;
	int32 Count = 0;
	for (const ASRUnit* Unit : Units)
	{
		if (Unit && Unit->IsAlive() && Unit->GetTeam() == Team)
		{
			Sum += Unit->GetPos2D();
			++Count;
		}
	}
	const USRFeelSettings& F = USRFeelSettings::Get();
	return Count > 0 ? Sum / Count : (Team == ESRTeam::Player ? F.PlayerStart : F.EnemyStart);
}

int32 USRBattleSubsystem::CountAlive(ESRTeam Team) const
{
	int32 Count = 0;
	for (const ASRUnit* Unit : Units)
	{
		if (Unit && Unit->IsAlive() && Unit->GetTeam() == Team) { ++Count; }
	}
	return Count;
}

void USRBattleSubsystem::LogStatus() const
{
	int32 Selected = 0;
	for (const ASRUnit* Unit : Units) { Selected += (Unit && Unit->IsSelected()) ? 1 : 0; }
	UE_LOG(LogSovereign, Log, TEXT("STATUS t=%.1f player=%d enemy=%d selected=%d result=%d autobattle=%d"),
		BattleClock, CountAlive(ESRTeam::Player), CountAlive(ESRTeam::Enemy), Selected, int32(Result), bAutoBattle ? 1 : 0);
	const APlayerController* PC = GetWorld()->GetFirstPlayerController();
	if (const ASRCameraPawn* Camera = PC ? Cast<ASRCameraPawn>(PC->GetPawn()) : nullptr)
	{
		const FVector Eye = PC->PlayerCameraManager ? PC->PlayerCameraManager->GetCameraLocation() : FVector::ZeroVector;
		const FRotator Rot = PC->PlayerCameraManager ? PC->PlayerCameraManager->GetCameraRotation() : FRotator::ZeroRotator;
		UE_LOG(LogSovereign, Log, TEXT("  CAMERA focus=(%.0f,%.0f,%.0f) dist=%.0f eye=(%.0f,%.0f,%.0f) pitch=%.1f yaw=%.1f"),
			Camera->GetFocusPoint().X, Camera->GetFocusPoint().Y, Camera->GetFocusPoint().Z, Camera->GetZoomDistance(), Eye.X, Eye.Y, Eye.Z, Rot.Pitch, Rot.Yaw);
	}
	for (const ASRUnit* Unit : Units)
	{
		if (!Unit) { continue; }
		static const TCHAR* AnimNames[] = { TEXT("spawn"), TEXT("idle"), TEXT("walk"), TEXT("attack"), TEXT("hit"), TEXT("death") };
		static const TCHAR* FacingNames[] = { TEXT("S"), TEXT("SW"), TEXT("W"), TEXT("NW"), TEXT("N"), TEXT("NE"), TEXT("E"), TEXT("SE") };
		UE_LOG(LogSovereign, Log, TEXT("  %-20s pos=(%7.0f,%7.0f,%5.0f) vel=%4.0f hp=%3.0f order=%d sel=%d target=%s sprite=%s:%d:%s"),
			*Unit->GetLabel(), Unit->GetSimPos().X, Unit->GetSimPos().Y, Unit->GetSimPos().Z, Unit->GetVelocity2D().Size(),
			Unit->GetHealth(), int32(Unit->GetOrder()), Unit->IsSelected() ? 1 : 0,
			Unit->GetTarget() ? *Unit->GetTarget()->GetLabel() : TEXT("-"),
			AnimNames[int32(Unit->GetSpriteAnim())], Unit->GetSpriteFrame(), FacingNames[Unit->GetSpriteFacing() % 8]);
	}
}

// ------------------------------------------------------------ debug inbox

void USRBattleSubsystem::PollCommandInbox(float DeltaTime)
{
#if !UE_BUILD_SHIPPING
	// Lets external tools (and automated checks) drive the game without a mouse:
	// write console commands, one per line, to <Project>/Saved/SRCommands.txt.
	InboxTimer -= DeltaTime;
	if (InboxTimer > 0.f) { return; }
	InboxTimer = 0.15f;

	const FString Path = FPaths::ProjectSavedDir() / TEXT("SRCommands.txt");
	if (!IFileManager::Get().FileExists(*Path)) { return; }

	TArray<FString> Lines;
	FFileHelper::LoadFileToStringArray(Lines, *Path);
	IFileManager::Get().Delete(*Path);
	for (const FString& Line : Lines)
	{
		const FString Command = Line.TrimStartAndEnd();
		if (!Command.IsEmpty() && GEngine)
		{
			UE_LOG(LogSovereign, Log, TEXT("INBOX > %s"), *Command);
			GEngine->Exec(GetWorld(), *Command);
		}
	}
#endif
}


// ------------------------------------------------------------------ group commands

ASRBuilding* USRBattleSubsystem::FindNearestEnemyBuilding(const ASRUnit* For, float Range) const
{
	const USREconomySubsystem* Eco = USREconomySubsystem::Get(this);
	if (!Eco || !For) { return nullptr; }
	ASRBuilding* Best = nullptr;
	float BestD = Range;
	for (ASRBuilding* B : Eco->GetBuildings())
	{
		if (!B || !B->IsAlive() || B->Team == For->GetTeam()) { continue; }
		const float D = B->DistanceToFootprint(For->GetPos2D());
		if (D < BestD) { BestD = D; Best = B; }
	}
	return Best;
}

void USRBattleSubsystem::CommandMove(const TArray<ASRUnit*>& Group, const FVector2D& Goal, bool bAttackMove, ESRFormationShape Shape, bool bAcknowledge,
	const FVector2D* Facing)
{
	TArray<ASRUnit*> Units2;
	for (ASRUnit* U : Group) { if (U && U->IsAlive()) { Units2.Add(U); } }
	if (Units2.Num() == 0) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();

	FVector2D Dest(FMath::Clamp(Goal.X, -F.MapHalfExtent.X, F.MapHalfExtent.X), FMath::Clamp(Goal.Y, -F.MapHalfExtent.Y, F.MapHalfExtent.Y));
	USRGridSubsystem* Grid = USRGridSubsystem::Get(this);
	if (Grid) { Dest = Grid->NearestWalkable(Dest); } // a click on a building, a rock or water means "go there", beside it

	TArray<FVector2D> Slots;
	SRFormation::ComputeSlots(Units2, Dest, Slots, Shape, Facing);

	TArray<FVector2D> Starts;
	for (ASRUnit* U : Units2) { Starts.Add(U->GetPos2D()); }
	TArray<TArray<FVector2D>> Paths;
	if (Grid) { Grid->FindGroupPaths(Starts, Dest, Paths); }
	for (int32 i = 0; i < Units2.Num(); ++i)
	{
		TArray<FVector2D> Path = Paths.IsValidIndex(i) ? Paths[i] : TArray<FVector2D>();
		FVector2D Slot = Grid ? Grid->NearestWalkable(Slots[i], 4) : Slots[i];
		Path.Add(Slot);
		Units2[i]->OrderMovePath(Path, bAttackMove);
		Units2[i]->SetHome(Slot);
		if (bAcknowledge) { Units2[i]->Acknowledge(FMath::FRandRange(0.f, F.AckMaxDelay)); }
	}
}

void USRBattleSubsystem::CommandAttack(const TArray<ASRUnit*>& Group, ASRUnit* Target)
{
	if (!Target) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	for (ASRUnit* U : Group)
	{
		if (U && U->IsAlive())
		{
			U->OrderAttack(Target);
			U->Acknowledge(FMath::FRandRange(0.f, F.AckMaxDelay));
		}
	}
}

void USRBattleSubsystem::CommandAttackBuilding(const TArray<ASRUnit*>& Group, ASRBuilding* Target)
{
	if (!Target) { return; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	for (ASRUnit* U : Group)
	{
		if (U && U->IsAlive())
		{
			U->OrderAttackBuilding(Target);
			U->Acknowledge(FMath::FRandRange(0.f, F.AckMaxDelay));
		}
	}
}
