// Copyright Sovereign Realms.

#include "FX/SRFXSprite.h"
#include "Battle/SRBattleSubsystem.h"
#include "Units/SRSprite.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Materials/MaterialInterface.h"

namespace
{
	// Frame counts / rates match SourceArt/FX/*.json (Tools/build_fx_materials.py reads the same files).
	const ASRFXSprite::FSpec Specs[] = {
		{ TEXT("Fire"), 8, 10.f, 64.f, 96.f, true, 0.f },
		{ TEXT("Smoke"), 8, 8.f, 64.f, 96.f, true, 0.f },
		{ TEXT("Dust"), 6, 12.f, 64.f, 40.f, false, 20.f },
		{ TEXT("Debris"), 6, 12.f, 96.f, 96.f, false, 0.f },
		{ TEXT("Impact"), 6, 12.f, 128.f, 96.f, false, 0.f },
	};
}

const ASRFXSprite::FSpec& ASRFXSprite::SpecFor(ESRFX InKind)
{
	return Specs[FMath::Clamp(int32(InKind), 0, int32(UE_ARRAY_COUNT(Specs)) - 1)];
}

ASRFXSprite::ASRFXSprite()
{
	PrimaryActorTick.bCanEverTick = true;
	Card = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Card"));
	SetRootComponent(Card);
	Card->SetMobility(EComponentMobility::Movable);
	Card->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Card->SetGenerateOverlapEvents(false);
	Card->SetCastShadow(false);
	Card->bReceivesDecals = false;
	Card->bAffectDynamicIndirectLighting = false;
	Card->bAffectDistanceFieldLighting = false;
	Card->bVisibleInRayTracing = false;
}

ASRFXSprite* ASRFXSprite::Spawn(UWorld* World, ESRFX InKind, const FVector& Location, float Scale, float InLifetime)
{
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(World);
	if (!World || !Battle || !Battle->UnitCardMesh) { return nullptr; }
	const FSpec& S = SpecFor(InKind);
	static TMap<int32, TWeakObjectPtr<UMaterialInterface>> Cache;
	TWeakObjectPtr<UMaterialInterface>& Mat = Cache.FindOrAdd(int32(InKind));
	if (!Mat.IsValid())
	{
		const FString Path = FString::Printf(TEXT("/Game/SR/Materials/MI_FX_%s.MI_FX_%s"), S.Name, S.Name);
		Mat = LoadObject<UMaterialInterface>(nullptr, *Path, nullptr, LOAD_NoWarn | LOAD_Quiet);
		if (!Mat.IsValid()) { return nullptr; }       // art not imported: no effect, nothing breaks
	}
	FActorSpawnParameters P;
	P.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	ASRFXSprite* FX = World->SpawnActor<ASRFXSprite>(Location, FRotator::ZeroRotator, P);
	if (!FX) { return nullptr; }
	FX->Kind = InKind;
	FX->Lifetime = InLifetime;
	FX->Phase = FMath::FRand() * S.Frames;      // loops start out of step with each other
	FX->Card->SetStaticMesh(Battle->UnitCardMesh);
	FX->Card->SetMaterial(0, Mat.Get());
	// the unit card holds a 160 px cell at the troops' 1.75 cm per pixel: size it to the strip's frame
	FX->Card->SetRelativeScale3D(FVector(1.f, S.WidthPx / 160.f * Scale, S.HeightPx / 160.f * Scale));
	FX->Tick(0.f);
	return FX;
}

void ASRFXSprite::Stop()
{
	if (StopAt < 0.f) { StopAt = Age; }
}

void ASRFXSprite::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	Age += DeltaSeconds;
	const FSpec& S = SpecFor(Kind);
	const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (Battle) { Card->SetWorldRotation(Battle->GetSpriteView().CardRotation); }
	if (S.Rise > 0.f) { AddActorWorldOffset(FVector(0.f, 0.f, S.Rise * DeltaSeconds)); }

	if (!S.bLoop && Age * S.Fps >= S.Frames) { Destroy(); return; }
	if (S.bLoop && Lifetime > 0.f && Age >= Lifetime) { Stop(); }
	float Fade = 1.f;
	if (StopAt >= 0.f)
	{
		Fade = 1.f - (Age - StopAt) / 0.5f;
		if (Fade <= 0.f) { Destroy(); return; }
	}
	const int32 Frame = S.bLoop ? int32(FMath::Fmod(Age * S.Fps + Phase, float(S.Frames))) : FMath::Min(int32(Age * S.Fps), S.Frames - 1);
	if (Frame != ShownFrame || !FMath::IsNearlyEqual(Fade, ShownFade, 0.02f))
	{
		ShownFrame = Frame;
		ShownFade = Fade;
		Card->SetCustomPrimitiveDataVector4(0, FVector4(float(Frame), 0.f, 0.f, Fade));
	}
}
