// Copyright Sovereign Realms.

#include "Common/SRAudioSubsystem.h"
#include "Common/SRFeelSettings.h"
#include "SovereignRealms.h"
#include "Sound/SoundBase.h"
#include "Sound/SoundAttenuation.h"
#include "Components/AudioComponent.h"
#include "Kismet/GameplayStatics.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/Pawn.h"
#include "Engine/World.h"

namespace
{
	struct FSoundRule
	{
		const TCHAR* Name;
		float MinGap;      // seconds between two plays
		float MaxLoad;     // how many may overlap (load decays at 1 per second per voice)
		float Volume;
		float PitchJitter;
	};

	const FSoundRule Rules[int32(ESRSound::Count)] = {
		{ TEXT("SwordHit"),        0.035f, 5.f, 0.80f, 0.08f },
		{ TEXT("ShieldBash"),      0.05f,  4.f, 0.80f, 0.07f },
		{ TEXT("BowRelease"),      0.03f,  5.f, 0.55f, 0.10f },
		{ TEXT("ArrowHitFlesh"),   0.04f,  4.f, 0.60f, 0.10f },
		{ TEXT("ArrowHitWood"),    0.04f,  4.f, 0.65f, 0.10f },
		{ TEXT("ArrowHitGround"),  0.05f,  3.f, 0.40f, 0.12f },
		{ TEXT("Death"),           0.06f,  3.f, 0.85f, 0.10f },
		{ TEXT("Select"),          0.06f,  2.f, 0.55f, 0.04f },
		{ TEXT("Acknowledge"),     0.10f,  2.f, 0.60f, 0.05f },
		{ TEXT("AttackOrder"),     0.10f,  2.f, 0.65f, 0.05f },
		{ TEXT("UIClick"),         0.03f,  3.f, 0.55f, 0.03f },
		{ TEXT("UIError"),         0.15f,  1.f, 0.60f, 0.00f },
		{ TEXT("CoinPayout"),      0.08f,  2.f, 0.55f, 0.06f },
		{ TEXT("GrainPayout"),     0.08f,  2.f, 0.50f, 0.06f },
		{ TEXT("BuildPlace"),      0.10f,  2.f, 0.80f, 0.04f },
		{ TEXT("BuildHammer"),     0.18f,  3.f, 0.45f, 0.12f },
		{ TEXT("BuildComplete"),   0.30f,  1.f, 0.75f, 0.00f },
		{ TEXT("RecruitReady"),    0.30f,  1.f, 0.60f, 0.03f },
		{ TEXT("BuildingHit"),     0.06f,  3.f, 0.55f, 0.10f },
		{ TEXT("BuildingCollapse"),0.30f,  2.f, 1.00f, 0.05f },
		{ TEXT("WarHorn"),         2.00f,  1.f, 0.80f, 0.00f },
		{ TEXT("Pickaxe"),         0.12f,  3.f, 0.30f, 0.10f },
		{ TEXT("Hoe"),             0.12f,  3.f, 0.25f, 0.10f },
		{ TEXT("Victory"),         2.00f,  1.f, 0.90f, 0.00f },
		{ TEXT("Defeat"),          2.00f,  1.f, 0.90f, 0.00f },
		{ TEXT("AmbientLoop"),     0.00f,  1.f, 1.00f, 0.00f },
		{ TEXT("MusicLoop"),       0.00f,  1.f, 1.00f, 0.00f },
	};
}

USRAudioSubsystem* USRAudioSubsystem::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<USRAudioSubsystem>() : nullptr;
}

bool USRAudioSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

TStatId USRAudioSubsystem::GetStatId() const
{
	RETURN_QUICK_DECLARE_CYCLE_STAT(USRAudioSubsystem, STATGROUP_Tickables);
}

void USRAudioSubsystem::OnWorldBeginPlay(UWorld& InWorld)
{
	Super::OnWorldBeginPlay(InWorld);
	Sounds.SetNum(int32(ESRSound::Count));
	for (int32 i = 0; i < int32(ESRSound::Count); ++i)
	{
		const FString Path = FString::Printf(TEXT("/Game/SR/Audio/S_%s.S_%s"), Rules[i].Name, Rules[i].Name);
		Sounds[i] = LoadObject<USoundBase>(nullptr, *Path, nullptr, LOAD_NoWarn | LOAD_Quiet);
	}
	// Positional falloff measured from the listener over the camera's focus point.
	Attenuation = NewObject<USoundAttenuation>(this);
	FSoundAttenuationSettings& A = Attenuation->Attenuation;
	A.bAttenuate = true;
	A.bSpatialize = true;
	A.AttenuationShape = EAttenuationShape::Sphere;
	A.AttenuationShapeExtents = FVector(900.f, 0.f, 0.f);
	A.FalloffDistance = FMath::Max(USRFeelSettings::Get().AudibleDistance - 900.f, 500.f);
	A.DistanceAlgorithm = EAttenuationDistanceModel::NaturalSound;
	A.NonSpatializedRadiusStart = 300.f;
	A.NonSpatializedRadiusEnd = 900.f;
	A.NonSpatializedRadiusMode = ENonSpatializedRadiusSpeakerMapMode::OmniDirectional;
	bLoaded = true;

	int32 Missing = 0;
	for (const TObjectPtr<USoundBase>& S : Sounds) { Missing += S ? 0 : 1; }
	if (Missing > 0)
	{
		UE_LOG(LogSovereign, Warning, TEXT("AUDIO %d of %d sounds missing under /Game/SR/Audio (run Tools/audio/gen_sounds.py and Tools/import_audio.py)"), Missing, Sounds.Num());
	}
}

void USRAudioSubsystem::Tick(float DeltaTime)
{
	for (float& L : VoiceLoad) { L = FMath::Max(0.f, L - DeltaTime); }

	// Listen from just above the camera's focus point, facing up the screen, so panning matches the view.
	if (APlayerController* PC = GetWorld()->GetFirstPlayerController())
	{
		if (const APawn* Pawn = PC->GetPawn())
		{
			Listener = Pawn->GetActorLocation() + FVector(0.f, 0.f, 500.f);
			PC->SetAudioListenerOverride(nullptr, Listener, FRotator(0.f, USRFeelSettings::Get().CameraYaw, 0.f));
		}
	}
}

USoundBase* USRAudioSubsystem::GetSound(ESRSound Sound)
{
	const int32 I = int32(Sound);
	return Sounds.IsValidIndex(I) ? Sounds[I].Get() : nullptr;
}

bool USRAudioSubsystem::IsUISound(ESRSound Sound) const
{
	switch (Sound)
	{
	case ESRSound::Select: case ESRSound::Acknowledge: case ESRSound::AttackOrder: case ESRSound::UIClick: case ESRSound::UIError:
	case ESRSound::BuildPlace: case ESRSound::Victory: case ESRSound::Defeat: case ESRSound::WarHorn: case ESRSound::RecruitReady:
		return true;
	default:
		return false;
	}
}

bool USRAudioSubsystem::Allow(ESRSound Sound)
{
	const int32 I = int32(Sound);
	const float Now = GetWorld()->GetRealTimeSeconds();
	if (Now - LastPlayed[I] < Rules[I].MinGap) { return false; }
	if (VoiceLoad[I] >= Rules[I].MaxLoad) { return false; }
	LastPlayed[I] = Now;
	VoiceLoad[I] += 1.f;
	return true;
}

void USRAudioSubsystem::PlayAt(ESRSound Sound, const FVector& Location, float VolumeScale)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	USoundBase* S = GetSound(Sound);
	if (!S || FVector2D::Distance(FVector2D(Location), FVector2D(Listener)) > F.AudibleDistance) { return; }
	if (!Allow(Sound)) { return; }
	const FSoundRule& R = Rules[int32(Sound)];
	const float Vol = F.MasterVolume * F.EffectsVolume * R.Volume * VolumeScale;
	const float Pitch = 1.f + FMath::FRandRange(-R.PitchJitter, R.PitchJitter);
	UGameplayStatics::PlaySoundAtLocation(this, S, Location, FRotator::ZeroRotator, Vol, Pitch, 0.f, Attenuation);
}

void USRAudioSubsystem::Play2D(ESRSound Sound, float VolumeScale)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	USoundBase* S = GetSound(Sound);
	if (!S || !Allow(Sound)) { return; }
	const FSoundRule& R = Rules[int32(Sound)];
	const float Bus = IsUISound(Sound) ? F.UIVolume : F.EffectsVolume;
	const float Pitch = 1.f + FMath::FRandRange(-R.PitchJitter, R.PitchJitter);
	UGameplayStatics::PlaySound2D(this, S, F.MasterVolume * Bus * R.Volume * VolumeScale, Pitch);
}

void USRAudioSubsystem::StartLoops()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (!AmbientComp && GetSound(ESRSound::AmbientLoop))
	{
		AmbientComp = UGameplayStatics::CreateSound2D(this, GetSound(ESRSound::AmbientLoop), F.MasterVolume * F.AmbientVolume, 1.f, 0.f, nullptr, true, false);
		if (AmbientComp) { AmbientComp->FadeIn(2.5f, F.MasterVolume * F.AmbientVolume); }
	}
	if (!MusicComp && GetSound(ESRSound::MusicLoop))
	{
		MusicComp = UGameplayStatics::CreateSound2D(this, GetSound(ESRSound::MusicLoop), F.MasterVolume * F.MusicVolume, 1.f, 0.f, nullptr, true, false);
		if (MusicComp) { MusicComp->FadeIn(4.f, F.MasterVolume * F.MusicVolume); }
	}
}

void USRAudioSubsystem::StopLoops()
{
	if (AmbientComp) { AmbientComp->FadeOut(1.f, 0.f); AmbientComp = nullptr; }
	if (MusicComp) { MusicComp->FadeOut(1.5f, 0.f); MusicComp = nullptr; }
}

void USRAudioSubsystem::RefreshLoopVolumes()
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	if (AmbientComp) { AmbientComp->SetVolumeMultiplier(F.MasterVolume * F.AmbientVolume); }
	if (MusicComp) { MusicComp->SetVolumeMultiplier(F.MasterVolume * F.MusicVolume); }
}
