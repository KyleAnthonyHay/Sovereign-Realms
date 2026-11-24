#include "VLArrow.h"
#include "VLArrowTrail.h"
#include "VLGrid.h"
#include "VLBattle.h"
#include "Components/CapsuleComponent.h"
#include "SovereignRealms.h"
#include "VLKing.h"
#include "VLSwordsmanCombat.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Engine/DamageEvents.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundBase.h"

namespace
{
	TAutoConsoleVariable<float> CVarArrowLife(TEXT("vl.Arrow.Life"), 2.f, TEXT("seconds an arrow stays where it landed before it is taken back"));
	TAutoConsoleVariable<float> CVarArrowFade(TEXT("vl.Arrow.Fade"), 0.5f, TEXT("it fades out over this many of those seconds (the last ones)"));
	TAutoConsoleVariable<float> CVarArrowMaxFlight(TEXT("vl.Arrow.MaxFlight"), 6.f, TEXT("an arrow that has hit nothing after this many seconds is taken back"));
	TAutoConsoleVariable<int32> CVarArrowPool(TEXT("vl.Arrow.Pool"), 96, TEXT("at most this many arrows at once (flying and stuck): beyond it the oldest is reused"));
	TAutoConsoleVariable<float> CVarArrowSink(TEXT("vl.Arrow.Sink"), 9.f, TEXT("cm an arrow's point goes into what it hits"));
	TAutoConsoleVariable<float> CVarArrowReleaseVolume(TEXT("vl.Arrow.ReleaseVolume"), 0.3f, TEXT("volume of the bow's twang, heard from close by"));
	TAutoConsoleVariable<float> CVarArrowDrawVolume(TEXT("vl.Arrow.DrawVolume"), 0.35f, TEXT("volume of the bow's creak as it is drawn"));
	TAutoConsoleVariable<float> CVarArrowDrawGap(TEXT("vl.Arrow.DrawGap"), 0.22f, TEXT("seconds at least between two creaks of bows being drawn (a volley's do not pile up)"));
	TAutoConsoleVariable<float> CVarArrowFlyVolume(TEXT("vl.Arrow.FlyVolume"), 0.1f, TEXT("volume of the arrow's whoosh as it leaves"));
	TAutoConsoleVariable<float> CVarArrowHitVolume(TEXT("vl.Arrow.HitVolume"), 0.26f, TEXT("volume of an arrow landing in wood or in the ground"));
	TAutoConsoleVariable<float> CVarArrowNear(TEXT("vl.Arrow.Near"), 900.f, TEXT("full volume within this many cm of where the player is looking"));
	TAutoConsoleVariable<float> CVarArrowRange(TEXT("vl.Arrow.Range"), 4500.f, TEXT("silent from this many cm"));
	TAutoConsoleVariable<float> CVarArrowSoundGap(TEXT("vl.Arrow.SoundGap"), 0.06f, TEXT("seconds at least between two sounds of a kind (a volley's sounds do not pile up)"));
	TAutoConsoleVariable<int32> CVarArrowTrail(TEXT("vl.Arrow.Trail"), 1, TEXT("1: every arrow in flight draws a pale streak along the stretch it has just flown; 0: none"));
	TAutoConsoleVariable<float> CVarArrowTrailLength(TEXT("vl.Arrow.TrailLength"), 0.4f, TEXT("seconds of its flight an arrow's streak shows (it tapers to nothing over them)"));
	TAutoConsoleVariable<float> CVarArrowTrailWidth(TEXT("vl.Arrow.TrailWidth"), 5.f, TEXT("cm the streak is wide at the arrow (never under a pixel and a half on screen)"));
	TAutoConsoleVariable<int32> CVarArcherLog(TEXT("vl.ArcherLog"), 0, TEXT("1: log every shot, every landing and every archery sound"));

	enum { ArrowSoundRelease, ArrowSoundFly, ArrowSoundWood, ArrowSoundGround, ArrowSoundDraw };

	void LoadArrowSounds(const TCHAR* Base, TArray<TObjectPtr<USoundBase>>& Out)
	{
		for (int32 i = 1; i <= 8; ++i)
		{
			const FString Name = i == 1 ? FString(Base) : FString::Printf(TEXT("%s_%d"), Base, i);
			if (USoundBase* S = LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/Voxel/Audio/%s.%s"), *Name, *Name), nullptr, LOAD_NoWarn | LOAD_Quiet))
			{
				Out.Add(S);
			}
		}
		if (Out.Num() == 0)
		{
			UE_LOG(LogSovereignRealms, Warning, TEXT("no %s sounds (copy them to SourceArt/Audio and run Tools/ue/import_audio.py)"), Base);
		}
	}
}

FTransform VLArrowGeom::MeshTransform(const FVector& Tip, const FVector& Along, float MeshYaw)
{
	// the mesh as the figure shows it (turned by MeshYaw) points along Dir from its origin, TipOffset behind the point
	const FVector Way = Along.GetSafeNormal(UE_SMALL_NUMBER, FVector::ForwardVector);
	const FQuat Turn = FQuat::FindBetweenNormals(Dir.GetSafeNormal(), Way);
	return FTransform(Turn * FRotator(0.f, MeshYaw, 0.f).Quaternion(), Tip - Way * TipOffset);
}

UVLArrows* UVLArrows::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UVLArrows>() : nullptr;
}

bool UVLArrows::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

bool UVLArrows::SolveArc(const FVector& From, const FVector& To, float Speed, float Gravity, FVector& OutDir)
{
	const FVector Flat(To.X - From.X, To.Y - From.Y, 0.f);
	const float X = Flat.Size();
	const float Y = To.Z - From.Z;
	if (X < 1.f)
	{
		OutDir = (To - From).GetSafeNormal(UE_SMALL_NUMBER, FVector::ForwardVector);
		return true;
	}
	const FVector Ahead = Flat / X;
	const float V2 = Speed * Speed;
	const float G = FMath::Max(Gravity, 1.f);
	const float Under = V2 * V2 - G * (G * X * X + 2.f * Y * V2);
	const bool bReach = Under >= 0.f;
	const float Angle = bReach ? FMath::Atan((V2 - FMath::Sqrt(Under)) / (G * X)) : UE_PI * 0.25f;
	OutDir = Ahead * FMath::Cos(Angle) + FVector::UpVector * FMath::Sin(Angle);
	return bReach;
}

float UVLArrows::ArcGravity(float FlatDistance, float Speed, float MaxGravity, float PeakHeight, float PeakDistance, float Growth)
{
	const float MaxG = FMath::Max(MaxGravity, 1.f);
	if (PeakHeight <= 0.f || PeakDistance <= 1.f || FlatDistance < 1.f || Speed < 1.f)
	{
		return MaxG;
	}
	// On level ground an arrow loosed at angle A lands X away with its top X tan(A) / 4 above the line, under the
	// pull g = v2 sin(2A) / X. So for the top wanted: tan(A) = 4 H / X, and sin(2A) = 2 t / (1 + t2).
	const float Peak = PeakHeight * FMath::Pow(FlatDistance / PeakDistance, FMath::Max(Growth, 0.f));
	const float T = 4.f * Peak / FlatDistance;
	const float G = Speed * Speed * (2.f * T / (1.f + T * T)) / FlatDistance;
	return FMath::Clamp(G, 1.f, MaxG);
}

void UVLArrows::Load()
{
	if (bLoaded)
	{
		return;
	}
	bLoaded = true;
	Mesh = LoadObject<UStaticMesh>(nullptr, VLArrowGeom::MeshPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
	FadeMaterial = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Voxel/Materials/M_VoxArrow.M_VoxArrow"), nullptr, LOAD_NoWarn | LOAD_Quiet);
	if (!Mesh)
	{
		UE_LOG(LogSovereignRealms, Warning, TEXT("arrows: no mesh at %s (import the archer)"), VLArrowGeom::MeshPath);
	}
	if (!FadeMaterial)
	{
		UE_LOG(LogSovereignRealms, Warning, TEXT("arrows: no M_VoxArrow (run Tools/ue/build_arrow_material.py): they shrink instead of fading"));
	}
	LoadArrowSounds(TEXT("S_BowRelease"), ReleaseSounds);
	LoadArrowSounds(TEXT("S_ArrowFly"), FlySounds);
	LoadArrowSounds(TEXT("S_ArrowHitWood"), WoodSounds);
	LoadArrowSounds(TEXT("S_ArrowHitGround"), GroundSounds);
	LoadArrowSounds(TEXT("S_BowDraw"), DrawSounds);
	// placed left and right by where it happens; how loud it is, is worked out in Play
	Pan = NewObject<USoundAttenuation>(this);
	Pan->Attenuation.bAttenuate = false;
	Pan->Attenuation.bSpatialize = true;
	if (UWorld* World = GetWorld())
	{
		Holder = World->SpawnActor<AActor>();
		if (Holder)
		{
			USceneComponent* Root = NewObject<USceneComponent>(Holder, TEXT("Root"));
			Holder->SetRootComponent(Root);
			Root->RegisterComponent();
			// the streaks behind the arrows: one mesh for all of them. Its material is made here from M_PlacementGhost
			// (translucent, unlit, two sided: emissive "Tint", "Opacity"), pale gold: no asset of its own
			Trail = NewObject<UVLArrowTrailComponent>(Holder, TEXT("Trails"));
			if (UMaterialInterface* Glow = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/Voxel/Materials/M_PlacementGhost.M_PlacementGhost"), nullptr, LOAD_NoWarn | LOAD_Quiet))
			{
				TrailMaterial = UMaterialInstanceDynamic::Create(Glow, this);
				TrailMaterial->SetVectorParameterValue(TEXT("Tint"), FLinearColor(1.f, 0.93f, 0.7f, 1.f));
				TrailMaterial->SetScalarParameterValue(TEXT("Opacity"), 0.6f);
				Trail->SetTrailMaterial(TrailMaterial);
			}
			else
			{
				UE_LOG(LogSovereignRealms, Warning, TEXT("arrows: no M_PlacementGhost (run Tools/ue/build_ghost_material.py): the streaks are drawn with the default material"));
			}
			Trail->SetupAttachment(Root);
			Trail->RegisterComponent();
		}
	}
}

void UVLArrows::Play(int32 Kind, const FVector& At, float Volume)
{
	UWorld* World = GetWorld();
	TArray<TObjectPtr<USoundBase>>& Set = Kind == ArrowSoundRelease ? ReleaseSounds : Kind == ArrowSoundFly ? FlySounds : Kind == ArrowSoundWood ? WoodSounds : Kind == ArrowSoundDraw ? DrawSounds : GroundSounds;
	if (!World || Set.Num() == 0)
	{
		return;
	}
	const double Now = World->GetTimeSeconds();
	if (LastTime[Kind] >= 0.0 && Now - LastTime[Kind] < (Kind == ArrowSoundDraw ? CVarArrowDrawGap : CVarArrowSoundGap).GetValueOnGameThread())
	{
		return;
	}
	const APlayerController* PC = World->GetFirstPlayerController();
	const AVLKing* Player = PC ? Cast<AVLKing>(PC->GetPawn()) : nullptr;
	const float Far = Player ? Player->ListenDistance(At) : 0.f;
	const float Near = CVarArrowNear.GetValueOnGameThread();
	const float Fade = FMath::Square(FMath::GetMappedRangeValueClamped(FVector2D(Near, FMath::Max(CVarArrowRange.GetValueOnGameThread(), Near + 1.f)), FVector2D(1.f, 0.f), Far));
	Volume *= Fade * FMath::FRandRange(0.8f, 1.f);
	if (Volume <= 0.004f)
	{
		return;
	}
	int32 Index = FMath::RandRange(0, Set.Num() - 1);
	if (Index == LastClip[Kind] && Set.Num() > 1)
	{
		Index = (Index + FMath::RandRange(1, Set.Num() - 1)) % Set.Num();       // never the same twice running
	}
	LastClip[Kind] = Index;
	LastTime[Kind] = Now;
	const float Pitch = FMath::FRandRange(0.94f, 1.06f);
	UGameplayStatics::PlaySoundAtLocation(World, Set[Index], At, Volume, Pitch, 0.f, Pan);
	if (CVarArcherLog.GetValueOnGameThread() != 0)
	{
		static const TCHAR* Names[5] = { TEXT("release"), TEXT("fly"), TEXT("wood"), TEXT("ground"), TEXT("draw") };
		UE_LOG(LogSovereignRealms, Log, TEXT("arrow sound t=%.3f %s clip %d vol %.3f, %.0f cm from the focus"), Now, Names[Kind], Index + 1, Volume, Far);
	}
}

int32 UVLArrows::Take()
{
	int32 Index = Arrows.IndexOfByPredicate([](const FArrow& A) { return A.State == EState::Free; });
	if (Index != INDEX_NONE)
	{
		return Index;
	}
	if (Arrows.Num() < FMath::Max(CVarArrowPool.GetValueOnGameThread(), 1) && Holder && Mesh)
	{
		UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(Holder);
		C->SetMobility(EComponentMobility::Movable);
		C->SetStaticMesh(Mesh);
		C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		C->SetGenerateOverlapEvents(false);
		C->SetCastShadow(false);
		C->bAffectDistanceFieldLighting = false;
		C->SetCanEverAffectNavigation(false);
		if (FadeMaterial)
		{
			for (int32 i = 0; i < C->GetNumMaterials(); ++i)
			{
				C->SetMaterial(i, FadeMaterial);
			}
			C->SetDefaultCustomPrimitiveDataFloat(0, 1.f);
		}
		C->SetupAttachment(Holder->GetRootComponent());
		C->RegisterComponent();
		C->SetVisibility(false);
		Components.Add(C);
		return Arrows.AddDefaulted();
	}
	// the pool is full: the one that landed longest ago, else the one longest in the air
	float Oldest = -1.f;
	for (int32 i = 0; i < Arrows.Num(); ++i)
	{
		const float Score = Arrows[i].Age + (Arrows[i].State == EState::Stuck ? 1000.f : 0.f);
		if (Score > Oldest)
		{
			Oldest = Score;
			Index = i;
		}
	}
	if (Index != INDEX_NONE)
	{
		Release(Index);
	}
	return Index;
}

void UVLArrows::Release(int32 Index)
{
	FArrow& A = Arrows[Index];
	UStaticMeshComponent* C = Components[Index];
	if (C)
	{
		C->SetVisibility(false);
		if (Holder && C->GetAttachParent() != Holder->GetRootComponent())
		{
			C->AttachToComponent(Holder->GetRootComponent(), FAttachmentTransformRules::KeepWorldTransform);
		}
	}
	A.State = EState::Free;
	A.Ignore = nullptr;
	A.Shooter = nullptr;
	A.Source = nullptr;
	A.Team = -1;
}

void UVLArrows::SetFade(int32 Index, float Alpha)
{
	FArrow& A = Arrows[Index];
	UStaticMeshComponent* C = Components[Index];
	if (!C || FMath::IsNearlyEqual(A.Shown, Alpha, 0.004f))
	{
		return;
	}
	A.Shown = Alpha;
	if (FadeMaterial)
	{
		C->SetCustomPrimitiveDataFloat(0, Alpha);
	}
	else
	{
		C->SetWorldScale3D(FVector(FMath::Max(Alpha, 0.01f)));
	}
}

void UVLArrows::Place(int32 Index)
{
	const FArrow& A = Arrows[Index];
	if (UStaticMeshComponent* C = Components[Index])
	{
		const FTransform T = VLArrowGeom::MeshTransform(A.Tip, A.Velocity);
		C->SetWorldLocationAndRotation(T.GetLocation(), T.GetRotation());
	}
}

void UVLArrows::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	for (TActorIterator<AActor> It(&InWorld); It; ++It)
	{
		if (It->ActorHasTag(TEXT("Dummy")))
		{
			DummyRest.Add(*It, It->GetActorQuat());
		}
	}
}

void UVLArrows::PlayDraw(const FVector& At)
{
	Load();
	Play(ArrowSoundDraw, At, CVarArrowDrawVolume.GetValueOnGameThread());
}

void UVLArrows::PlaySwish(const FVector& At)
{
	Load();
	Play(ArrowSoundFly, At, CVarArrowFlyVolume.GetValueOnGameThread() * 1.6f);
}

void UVLArrows::BashDummy(AActor* Dummy, const FVector& Away, float Degrees, float Damage, AVLKing* By)
{
	if (!Dummy)
	{
		return;
	}
	Load();
	FKnock* K = Knocks.FindByPredicate([Dummy](const FKnock& X) { return X.Actor.Get() == Dummy; });
	if (!K)
	{
		K = &Knocks.AddDefaulted_GetRef();
		K->Actor = Dummy;
		const FQuat* Rest = DummyRest.Find(Dummy);
		K->Rest = Rest ? *Rest : Dummy->GetActorQuat();
	}
	K->Away = Away.GetSafeNormal2D(UE_SMALL_NUMBER, FVector::ForwardVector);
	K->Degrees = Degrees;
	K->Time = 0.f;
	Play(ArrowSoundWood, Dummy->GetActorLocation() + FVector(0.f, 0.f, 90.f), CVarArrowHitVolume.GetValueOnGameThread() * 0.7f);
	UGameplayStatics::ApplyDamage(Dummy, Damage, By ? By->GetController() : nullptr, By, nullptr);
	UE_LOG(LogSovereignRealms, Log, TEXT("%s bashes %s with the bow (damage %.0f)"), By ? *By->GetDisplayName() : TEXT("-"), *Dummy->GetName(), Damage);
}

void UVLArrows::Fire(AVLKing* Shooter, const FVector& Tip, const FVector& Velocity, float Gravity, AActor* Ignore, float Damage)
{
	Load();
	const int32 Index = Take();
	if (Index == INDEX_NONE)
	{
		return;
	}
	FArrow& A = Arrows[Index];
	A.State = EState::Flying;
	A.Tip = Tip;
	A.Velocity = Velocity;
	A.Gravity = Gravity;
	A.Damage = Damage;
	A.Age = 0.f;
	A.Ignore = Ignore;
	A.Shooter = Shooter;
	A.Source = Shooter;
	A.Team = Shooter ? Shooter->Team : -1;
	A.Shown = -1.f;
	if (UStaticMeshComponent* C = Components[Index])
	{
		C->SetWorldScale3D(FVector::OneVector);
		C->SetVisibility(true);
	}
	SetFade(Index, 1.f);
	Place(Index);
	++Fired;
	Play(ArrowSoundRelease, Tip, CVarArrowReleaseVolume.GetValueOnGameThread());
	Play(ArrowSoundFly, Tip, CVarArrowFlyVolume.GetValueOnGameThread());
}

void UVLArrows::FireFrom(AActor* Source, int32 Team, const FVector& Tip, const FVector& Velocity, float Gravity, float Damage)
{
	Fire(nullptr, Tip, Velocity, Gravity, Source, Damage);
	// (Fire took the newest free arrow: find it again and give it its side)
	for (FArrow& A : Arrows)
	{
		if (A.State == EState::Flying && A.Age == 0.f && A.Ignore.Get() == Source && !A.Source.IsValid())
		{
			A.Source = Source;
			A.Team = Team;
		}
	}
}

AVLKing* UVLArrows::UnitOnPath(const FArrow& A, const FVector& From, const FVector& To, float& OutT) const
{
	if (A.Team < 0)
	{
		return nullptr;
	}
	AVLKing* Best = nullptr;
	OutT = 2.f;
	const FVector Seg = To - From;
	const double SegSize = Seg.Size(), SegSizeSquared = Seg.SizeSquared();
	// (B: only the units whose cells this stretch of flight passes over, from the battle's spatial hash, a body's
	// width to either side; in the registry's order. The tests below are as they were for every unit)
	const UVLBattle* Battle = UVLBattle::Get(this);
	FVLUnits Near;
	if (Battle)
	{
		const float Pad = 250.f;
		Battle->UnitsInBox(FVector2D(FMath::Min(From.X, To.X) - Pad, FMath::Min(From.Y, To.Y) - Pad), FVector2D(FMath::Max(From.X, To.X) + Pad, FMath::Max(From.Y, To.Y) + Pad), Near);
	}
	else
	{
		for (TActorIterator<AVLKing> It(GetWorld()); It; ++It)
		{
			Near.Add(*It);
		}
	}
	const AVLKing* Shooter = A.Shooter.Get();
	for (AVLKing* U : Near)
	{
		if (!U->IsAlive() || U->Team == A.Team || U->Team < 0 || U == Shooter)
		{
			continue;
		}
		// the body: a vertical segment from its feet to its head, with its capsule's radius (and a little more)
		const UCapsuleComponent* Cap = U->GetCapsuleComponent();
		const float Half = Cap->GetScaledCapsuleHalfHeight(), Rad = Cap->GetScaledCapsuleRadius() + 14.f;
		const FVector C = U->GetActorLocation();
		if (FVector::DistSquared(C, From) > FMath::Square(SegSize + Half + Rad + 50.f))
		{
			continue;
		}
		FVector OnArrow, OnBody;
		FMath::SegmentDistToSegmentSafe(From, To, C - FVector(0.f, 0.f, Half * 0.9f), C + FVector(0.f, 0.f, Half * 0.9f), OnArrow, OnBody);
		if (FVector::DistSquared(OnArrow, OnBody) <= FMath::Square(Rad))
		{
			const float T = SegSizeSquared > 1.f ? FVector::DotProduct(OnArrow - From, Seg) / SegSizeSquared : 0.f;
			if (T < OutT)
			{
				OutT = T;
				Best = U;
			}
		}
	}
	return Best;
}

void UVLArrows::Land(int32 Index, const FHitResult& Hit)
{
	FArrow& A = Arrows[Index];
	EndTrail(A, Hit.ImpactPoint);
	const FVector Way = A.Velocity.GetSafeNormal(UE_SMALL_NUMBER, FVector::ForwardVector);
	AActor* Struck = Hit.GetActor();
	const AVLKing* By = A.Shooter.Get();
	const bool bLog = CVarArcherLog.GetValueOnGameThread() != 0;
	// (the water stops no trace: an arrow that comes down on the bed of the river or the sea went into the water)
	const UVLGrid* Grid = UVLGrid::Get(this);
	if ((Struck && Struck->ActorHasTag(TEXT("Water"))) || (Grid && Grid->WaterLevelAt(Hit.ImpactPoint) > Hit.ImpactPoint.Z + 10.f))
	{
		if (bLog)
		{
			UE_LOG(LogSovereignRealms, Log, TEXT("arrow of %s lost in the water at %s after %.2f s"), By ? *By->GetDisplayName() : TEXT("-"), *Hit.ImpactPoint.ToCompactString(), A.Age);
		}
		Release(Index);
		return;
	}
	A.Tip = Hit.ImpactPoint + Way * CVarArrowSink.GetValueOnGameThread();
	if (A.Damage > 0.f && A.Team >= 0)
	{
		if (UVLBattle* Battle = UVLBattle::Get(this))
		{
			AActor* Target = Struck;
			if (!Target || !Battle->FindBuilding(Target))
			{
				// a prop, the mound, the ground at its foot, a hidden wall: inside a foe's building's hit box it is the building
				if (AActor* Wall = Battle->BuildingAt(Hit.ImpactPoint, A.Team))
				{
					Target = Wall;
				}
			}
			if (Target)
			{
				Battle->DamageAt(Target, A.Damage, A.Source.Get(), A.Team, Hit.ImpactPoint, Way);     // a foe's building (a castle: its corner, if it lands in one) (never a friend's; dummies have no health)
			}
		}
	}
	A.State = EState::Stuck;
	const float Flight = A.Age;
	A.Age = 0.f;
	Place(Index);
	const bool bDummy = Struck && Struck->ActorHasTag(TEXT("Dummy"));
	if (bDummy)
	{
		// it rides the dummy as it rocks
		if (UStaticMeshComponent* C = Components[Index])
		{
			if (USceneComponent* Root = Struck->GetRootComponent())
			{
				C->AttachToComponent(Root, FAttachmentTransformRules::KeepWorldTransform);
			}
		}
		++DummyHits;
		if (UVLSwordFx* Fx = UVLSwordFx::Get(this))
		{
			Fx->HitDummy(Struck, FVector(Way.X, Way.Y, 0.f).GetSafeNormal(UE_SMALL_NUMBER, FVector::ForwardVector), By);
		}
	}
	else
	{
		const bool bWood = By && By->SurfaceUnder(A.Tip - Way * 20.f + FVector(0.f, 0.f, 12.f)) == EVLStepSurface::Wood;
		Play(bWood ? ArrowSoundWood : ArrowSoundGround, A.Tip, CVarArrowHitVolume.GetValueOnGameThread());
	}
	if (bLog || bDummy)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("arrow of %s %s %s at %s after %.2f s (damage %.0f)"), By ? *By->GetDisplayName() : TEXT("-"), bDummy ? TEXT("sticks in dummy") : TEXT("lands on"),
			Struck ? *Struck->GetName() : TEXT("nothing"), *Hit.ImpactPoint.ToCompactString(), Flight, A.Damage);
	}
}

void UVLArrows::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	UWorld* World = GetWorld();
	if (!World || DeltaSeconds <= 0.f)
	{
		return;
	}
	FVLOptTiming::FScope Timing(FVLOptTiming::Arrows);
	// dummies knocked by a bow: a small rock on the foot, settling back to how they stood
	for (int32 i = Knocks.Num() - 1; i >= 0; --i)
	{
		FKnock& K = Knocks[i];
		AActor* Dummy = K.Actor.Get();
		K.Time += DeltaSeconds;
		if (!Dummy || K.Time > 1.3f)
		{
			if (Dummy)
			{
				Dummy->SetActorRotation(K.Rest);
			}
			Knocks.RemoveAtSwap(i);
			continue;
		}
		const float Tilt = K.Degrees * FMath::Exp(-4.f * K.Time) * FMath::Cos(K.Time * 15.f - 0.6f);
		const FVector Axis = FVector::CrossProduct(FVector::UpVector, K.Away).GetSafeNormal();
		Dummy->SetActorRotation(FQuat(Axis, FMath::DegreesToRadians(Tilt)) * K.Rest);
	}
	const float Life = FMath::Max(CVarArrowLife.GetValueOnGameThread(), 0.05f);
	const float FadeFor = FMath::Clamp(CVarArrowFade.GetValueOnGameThread(), 0.01f, Life);
	const float MaxFlight = CVarArrowMaxFlight.GetValueOnGameThread();
	// (B: where every unit stands now, once for all the arrows of this tick)
	if (const UVLBattle* Battle = UVLBattle::Get(this); Battle && Arrows.ContainsByPredicate([](const FArrow& A) { return A.State == EState::Flying; }))
	{
		Battle->RefreshUnitHash();
	}
	for (int32 i = 0; i < Arrows.Num(); ++i)
	{
		FArrow& A = Arrows[i];
		if (A.State == EState::Free)
		{
			continue;
		}
		A.Age += DeltaSeconds;
		if (A.State == EState::Stuck)
		{
			if (A.Age >= Life)
			{
				Release(i);
			}
			else if (A.Age > Life - FadeFor)
			{
				SetFade(i, (Life - A.Age) / FadeFor);
			}
			continue;
		}
		if (A.Age > MaxFlight || A.Tip.Z < -30000.f)
		{
			if (CVarArcherLog.GetValueOnGameThread() != 0)
			{
				UE_LOG(LogSovereignRealms, Log, TEXT("arrow lost at %s after %.2f s"), *A.Tip.ToCompactString(), A.Age);
			}
			EndTrail(A, A.Tip);
			Release(i);
			continue;
		}
		const FVector From = A.Tip;
		const FVector NewVelocity = A.Velocity - FVector(0.f, 0.f, A.Gravity * DeltaSeconds);
		const FVector To = From + (A.Velocity + NewVelocity) * 0.5f * DeltaSeconds;
		FCollisionQueryParams Params(SCENE_QUERY_STAT(VLArrow), true);
		if (const AActor* Shooter = A.Shooter.Get())
		{
			Params.AddIgnoredActor(Shooter);
		}
		if (A.Age < 0.5f)
		{
			if (const AActor* Ignore = A.Ignore.Get())
			{
				Params.AddIgnoredActor(Ignore);     // out over the rail of the tower it was loosed from
			}
		}
		FHitResult Hit;
		const bool bHit = World->LineTraceSingleByChannel(Hit, From, To, ECC_Visibility, Params);
		// a foe's body in the way, before whatever the trace met (units do not stop a visibility trace)
		float T = 2.f;
		if (AVLKing* Foe = UnitOnPath(A, From, To, T); Foe && (!bHit || T <= Hit.Time))
		{
			if (UVLBattle* Battle = UVLBattle::Get(this))
			{
				Battle->Damage(Foe, A.Damage, A.Source.Get(), A.Team);
				Battle->PlayAt(TEXT("S_ArrowHitFlesh"), Foe->GetActorLocation(), 0.4f, 3500.f, 0.05f);
			}
			if (CVarArcherLog.GetValueOnGameThread() != 0)
			{
				UE_LOG(LogSovereignRealms, Log, TEXT("arrow strikes %s after %.2f s (damage %.0f)"), *Foe->GetDisplayName(), A.Age, A.Damage);
			}
			EndTrail(A, From + (To - From) * FMath::Clamp(T, 0.f, 1.f));
			Release(i);
			continue;
		}
		// a foe's building: its hit box (grown past its walls and eaves, VLRules::BuildingHitPad), not only its mesh's
		// collision, which props, the mound or a hidden wall can stand in front of
		if (A.Team >= 0 && A.Damage > 0.f)
		{
			float BT = 2.f;
			if (UVLBattle* Battle = UVLBattle::Get(this))
			{
				if (AActor* Wall = Battle->BuildingOnPath(From, To, A.Team, BT); Wall && (!bHit || BT <= Hit.Time + 0.02f))
				{
					if (bHit && Hit.GetActor() == Wall)
					{
						Land(i, Hit);           // its own mesh, where the trace met it: it sticks there (Land does the damage)
						continue;
					}
					// into the box short of anything solid (by its walls, under its eaves): struck, the arrow is spent
					// (S_BuildingHit is the battle's)
					Battle->DamageAt(Wall, A.Damage, A.Source.Get(), A.Team, From + (To - From) * FMath::Clamp(BT, 0.f, 1.f), To - From);
					if (CVarArcherLog.GetValueOnGameThread() != 0)
					{
						UE_LOG(LogSovereignRealms, Log, TEXT("arrow strikes building %s after %.2f s (damage %.0f)"), *Wall->GetName(), A.Age, A.Damage);
					}
					EndTrail(A, From + (To - From) * FMath::Clamp(BT, 0.f, 1.f));
					Release(i);
					continue;
				}
			}
		}
		if (bHit)
		{
			Land(i, Hit);
			continue;
		}
		A.Tip = To;
		A.Velocity = NewVelocity;
		Place(i);
	}
	UpdateTrails(DeltaSeconds);
}

void UVLArrows::EndTrail(const FArrow& A, const FVector& At)
{
	if (CVarArrowTrail.GetValueOnGameThread() == 0 || A.State != EState::Flying || A.Age <= 0.f)
	{
		return;
	}
	FTail& Tail = Tails.AddDefaulted_GetRef();
	Tail.End = At;
	Tail.Velocity = A.Velocity;
	Tail.Gravity = A.Gravity;
	Tail.Flight = A.Age;
}

void UVLArrows::UpdateTrails(float DeltaSeconds)
{
	if (!Trail)
	{
		return;
	}
	const float Length = FMath::Clamp(CVarArrowTrailLength.GetValueOnGameThread(), 0.02f, 5.f);
	const bool bOn = CVarArrowTrail.GetValueOnGameThread() != 0;
	for (int32 i = Tails.Num() - 1; i >= 0; --i)
	{
		Tails[i].Since += DeltaSeconds;
		if (!bOn || Tails[i].Since >= Length)
		{
			Tails.RemoveAtSwap(i);
		}
	}
	// A streak is PerTrail points of the arc the arrow has flown, from Newest to Oldest seconds ago. The flight is a
	// parabola, so where it was U seconds before End (flying on at Velocity there) is End - Velocity U - (0, 0, Gravity U2 / 2).
	constexpr int32 PerTrail = 9;
	TArray<UVLArrowTrailComponent::FPoint> Points;
	FVector Origin = FVector::ZeroVector;
	FBox Box(ForceInit);
	bool bFirst = true;
	auto Add = [&](const FVector& End, const FVector& Velocity, float Gravity, float Since, float Newest, float Oldest)
	{
		if (Oldest - Newest < 0.004f)
		{
			return;
		}
		if (bFirst)
		{
			bFirst = false;
			Origin = End;
		}
		for (int32 k = 0; k < PerTrail; ++k)
		{
			const float Ago = FMath::Lerp(Newest, Oldest, float(k) / float(PerTrail - 1));
			const float Back = Ago - Since;
			const FVector At = End - Velocity * Back - FVector(0.f, 0.f, 0.5f * Gravity * Back * Back);
			Box += At;
			UVLArrowTrailComponent::FPoint& P = Points.AddDefaulted_GetRef();
			P.At = FVector3f(At - Origin);
			P.Width = FMath::Clamp(1.f - Ago / Length, 0.f, 1.f);
		}
	};
	if (bOn)
	{
		for (const FArrow& A : Arrows)
		{
			if (A.State == EState::Flying)
			{
				// (from a little behind the point, inside the shaft, back to the bow at most)
				const float Speed = A.Velocity.Size();
				Add(A.Tip, A.Velocity, A.Gravity, 0.f, Speed > 1.f ? FMath::Min(VLArrowGeom::TipOffset / Speed, A.Age) : 0.f, FMath::Min(Length, A.Age));
			}
		}
		for (const FTail& T : Tails)
		{
			Add(T.End, T.Velocity, T.Gravity, T.Since, T.Since, FMath::Min(Length, T.Since + T.Flight));
		}
	}
	if (Points.Num() > 0)
	{
		Box = Box.ExpandBy(50.f);
	}
	Trail->SetTrails(MoveTemp(Points), PerTrail, Origin, Box, FMath::Max(CVarArrowTrailWidth.GetValueOnGameThread(), 0.1f) * 0.5f);
}

int32 UVLArrows::NumFlying() const
{
	return Arrows.FilterByPredicate([](const FArrow& A) { return A.State == EState::Flying; }).Num();
}

int32 UVLArrows::NumStuck() const
{
	return Arrows.FilterByPredicate([](const FArrow& A) { return A.State == EState::Stuck; }).Num();
}

namespace
{
	FAutoConsoleCommandWithWorldAndArgs CmdArrows(TEXT("vl.Arrows"), TEXT("log the arrows: how many are flying, stuck, in the pool, loosed so far and how many stuck in a dummy"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			if (const UVLArrows* Arrows = UVLArrows::Get(World))
			{
				UE_LOG(LogSovereignRealms, Log, TEXT("arrows: %d flying, %d stuck, pool %d, loosed %d, in a dummy %d"), Arrows->NumFlying(), Arrows->NumStuck(), Arrows->PoolSize(),
					Arrows->NumFired(), Arrows->NumDummyHits());
			}
		}));
}
