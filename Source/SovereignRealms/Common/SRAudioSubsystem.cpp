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
#include "Player/SRCameraPawn.h"
#include "Curves/RichCurve.h"

namespace
{
	struct FSoundRule
	{
		const TCHAR* Name;
		float MinGap;      // seconds between two plays
		float MaxLoad;     // how many may overlap (load decays at 1 per second per voice)
		float Volume;
		float PitchJitter;
		float Range;       // cm it carries (x SoundRangeScale); 0 = not positioned
	};

	const FSoundRule Rules[int32(ESRSound::Count)] = {
		{ TEXT("SwordHit"),        0.035f, 5.f, 0.80f, 0.08f, 3200.f },
		{ TEXT("ShieldBash"),      0.05f,  4.f, 0.80f, 0.07f, 3200.f },
		{ TEXT("BowRelease"),      0.03f,  5.f, 0.55f, 0.10f, 3000.f },
		{ TEXT("ArrowHitFlesh"),   0.04f,  4.f, 0.60f, 0.10f, 2600.f },
		{ TEXT("ArrowHitWood"),    0.04f,  4.f, 0.65f, 0.10f, 2600.f },
		{ TEXT("ArrowHitGround"),  0.05f,  3.f, 0.40f, 0.12f, 2200.f },
		{ TEXT("Death"),           0.06f,  3.f, 0.85f, 0.10f, 3500.f },
		{ TEXT("Select"),          0.06f,  2.f, 0.55f, 0.04f, 0.f },
		{ TEXT("Acknowledge"),     0.10f,  2.f, 0.60f, 0.05f, 0.f },
		{ TEXT("AttackOrder"),     0.10f,  2.f, 0.65f, 0.05f, 0.f },
		{ TEXT("UIClick"),         0.03f,  3.f, 0.55f, 0.03f, 0.f },
		{ TEXT("UIError"),         0.15f,  1.f, 0.60f, 0.00f, 0.f },
		{ TEXT("CoinPayout"),      0.08f,  2.f, 0.55f, 0.06f, 3000.f },
		{ TEXT("GrainPayout"),     0.08f,  2.f, 0.50f, 0.06f, 3000.f },
		{ TEXT("BuildPlace"),      0.10f,  2.f, 0.80f, 0.04f, 4500.f },
		{ TEXT("BuildHammer"),     0.18f,  3.f, 0.40f, 0.08f, 2800.f },
		{ TEXT("BuildComplete"),   0.30f,  1.f, 0.75f, 0.00f, 0.f },
		{ TEXT("RecruitReady"),    0.30f,  1.f, 0.60f, 0.03f, 4500.f },
		{ TEXT("BuildingHit"),     0.06f,  3.f, 0.55f, 0.10f, 4000.f },
		{ TEXT("BuildingCollapse"),0.30f,  2.f, 1.00f, 0.05f, 9000.f },
		{ TEXT("WarHorn"),         2.00f,  1.f, 0.80f, 0.00f, 0.f },
		{ TEXT("Pickaxe"),         0.12f,  3.f, 0.30f, 0.10f, 1800.f },
		{ TEXT("Hoe"),             0.12f,  3.f, 0.25f, 0.10f, 1600.f },
		{ TEXT("Victory"),         2.00f,  1.f, 0.90f, 0.00f, 0.f },
		{ TEXT("Defeat"),          2.00f,  1.f, 0.90f, 0.00f, 0.f },
		{ TEXT("AmbientLoop"),     0.00f,  1.f, 1.00f, 0.00f, 0.f },
		{ TEXT("MusicLoop"),       0.00f,  1.f, 1.00f, 0.00f, 0.f },
		{ TEXT("ArrowFly"),        0.07f,  4.f, 0.40f, 0.10f, 2000.f },
		{ TEXT("SwordSwing"),      0.04f,  4.f, 0.50f, 0.10f, 2400.f },
		{ TEXT("HorseSnort"),      0.80f,  2.f, 0.55f, 0.08f, 2000.f },
		{ TEXT("GallopLoop"),      0.00f,  3.f, 0.55f, 0.06f, 3800.f },
		{ TEXT("CatapultBreak"),   0.20f,  2.f, 0.90f, 0.06f, 5000.f },
		{ TEXT("FireLoop"),        0.00f,  4.f, 0.50f, 0.05f, 2600.f },
		{ TEXT("FireCrackle"),     0.40f,  2.f, 0.55f, 0.10f, 3000.f },
		{ TEXT("MarchLoop"),       0.00f,  3.f, 0.50f, 0.00f, 3200.f },
		{ TEXT("HorseNeigh"),      1.50f,  2.f, 0.70f, 0.08f, 4000.f },
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
	Sounds.Reset();
	Attenuations.SetNum(int32(ESRSound::Count));
	const USRFeelSettings& F = USRFeelSettings::Get();
	for (int32 i = 0; i < int32(ESRSound::Count); ++i)
	{
		Variants[i].Reset();
		for (int32 v = 1; v <= 6; ++v)
		{
			const FString Name = v == 1 ? FString::Printf(TEXT("S_%s"), Rules[i].Name) : FString::Printf(TEXT("S_%s_%d"), Rules[i].Name, v);
			USoundBase* Wave = LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/SR/Audio/%s.%s"), *Name, *Name), nullptr, LOAD_NoWarn | LOAD_Quiet);
			if (!Wave) { break; }
			Sounds.Add(Wave);
			Variants[i].Add(Wave);
		}
		// Falloff from the listener: full volume close in, then a smooth curve down to silence at the sound's range,
		// so a sound never stops dead when the camera moves away from it; it fades out as it crosses the line.
		const float Range = Rules[i].Range * F.SoundRangeScale;
		if (Range <= 0.f) { continue; }
		USoundAttenuation* Att = NewObject<USoundAttenuation>(this);
		FSoundAttenuationSettings& A = Att->Attenuation;
		A.bAttenuate = true;
		A.bSpatialize = true;
		A.AttenuationShape = EAttenuationShape::Sphere;
		A.AttenuationShapeExtents = FVector(Range * 0.18f, 0.f, 0.f);
		A.FalloffDistance = Range * 0.82f;
		A.DistanceAlgorithm = EAttenuationDistanceModel::Custom;
		FRichCurve* Curve = A.CustomAttenuationCurve.GetRichCurve();
		Curve->Reset();
		const float Keys[][2] = { { 0.f, 1.f }, { 0.3f, 0.74f }, { 0.6f, 0.38f }, { 0.85f, 0.1f }, { 1.f, 0.f } };
		for (const auto& K : Keys) { Curve->SetKeyInterpMode(Curve->AddKey(K[0], K[1]), RCIM_Cubic); }
		A.NonSpatializedRadiusStart = 300.f;
		A.NonSpatializedRadiusEnd = 900.f;
		A.NonSpatializedRadiusMode = ENonSpatializedRadiusSpeakerMapMode::OmniDirectional;
		Attenuations[i] = Att;
	}
	bLoaded = true;

	int32 Missing = 0;
	for (int32 i = 0; i < int32(ESRSound::Count); ++i) { Missing += Variants[i].Num() == 0 ? 1 : 0; }
	if (Missing > 0)
	{
		UE_LOG(LogSovereign, Warning, TEXT("AUDIO %d of %d sounds missing under /Game/SR/Audio (run Tools/audio/gen_sounds.py, Tools/audio/prep_recorded.py and Tools/import_audio.py)"), Missing, int32(ESRSound::Count));
	}
}

void USRAudioSubsystem::Tick(float DeltaTime)
{
	for (float& L : VoiceLoad) { L = FMath::Max(0.f, L - DeltaTime); }
	Loops.RemoveAll([](const TWeakObjectPtr<UAudioComponent>& C) { return !C.IsValid() || !C->IsPlaying(); });

	// Listen from just above the camera's focus point, facing up the screen, so panning matches the view.
	if (APlayerController* PC = GetWorld()->GetFirstPlayerController())
	{
		if (const APawn* Pawn = PC->GetPawn())
		{
			// higher as the camera pulls back: zoomed out, small sounds fall out of reach and only big ones carry
			const ASRCameraPawn* Camera = Cast<ASRCameraPawn>(Pawn);
			const float Height = 400.f + (Camera ? Camera->GetZoomDistance() * USRFeelSettings::Get().ListenerZoomHeight : 300.f);
			Listener = Pawn->GetActorLocation() + FVector(0.f, 0.f, Height);
			PC->SetAudioListenerOverride(nullptr, Listener, FRotator(0.f, USRFeelSettings::Get().CameraYaw, 0.f));
		}
	}
}

USoundBase* USRAudioSubsystem::GetSound(ESRSound Sound)
{
	const int32 I = int32(Sound);
	if (I < 0 || I >= int32(ESRSound::Count) || Variants[I].Num() == 0) { return nullptr; }
	return Variants[I][FMath::RandRange(0, Variants[I].Num() - 1)];
}

float USRAudioSubsystem::RangeOf(ESRSound Sound) const
{
	return Rules[FMath::Clamp(int32(Sound), 0, int32(ESRSound::Count) - 1)].Range * USRFeelSettings::Get().SoundRangeScale;
}

bool USRAudioSubsystem::IsInRange(ESRSound Sound, const FVector& Location, float Slack) const
{
	const float R = RangeOf(Sound);
	return R <= 0.f || FVector::DistSquared(Location, Listener) < FMath::Square(R * Slack);
}

UAudioComponent* USRAudioSubsystem::PlayAttached(ESRSound Sound, USceneComponent* AttachTo, float VolumeScale, float PitchScale, float FadeIn)
{
	if (!AttachTo) { return nullptr; }
	const USRFeelSettings& F = USRFeelSettings::Get();
	USoundBase* S = GetSound(Sound);
	const int32 I = int32(Sound);
	if (!S || !IsInRange(Sound, AttachTo->GetComponentLocation())) { return nullptr; }
	const bool bLoop = S->IsLooping();
	if (bLoop)
	{
		int32 Running = 0;
		for (const TWeakObjectPtr<UAudioComponent>& C : Loops) { Running += (C.IsValid() && C->Sound && C->IsPlaying() && Variants[I].Contains(C->Sound.Get())) ? 1 : 0; }
		if (Running >= FMath::RoundToInt(Rules[I].MaxLoad)) { return nullptr; }   // for a loop, MaxLoad caps how many play at once
	}
	else if (!Allow(Sound)) { return nullptr; }
	const FSoundRule& R = Rules[I];
	const float Vol = F.MasterVolume * F.EffectsVolume * R.Volume * VolumeScale;
	const float Pitch = PitchScale * (1.f + FMath::FRandRange(-R.PitchJitter, R.PitchJitter));
	UAudioComponent* C = UGameplayStatics::SpawnSoundAttached(S, AttachTo, NAME_None, FVector::ZeroVector, EAttachLocation::KeepRelativeOffset, false,
		FadeIn > 0.f ? 0.f : Vol, Pitch, 0.f, Attenuations[I], nullptr, true);   // a loop is destroyed once faded out
	if (C && FadeIn > 0.f) { C->FadeIn(FadeIn, Vol); }
	if (C && bLoop) { Loops.Add(C); }
	return C;
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

float USRAudioSubsystem::BaseVolume(ESRSound Sound) const
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	return F.MasterVolume * F.EffectsVolume * Rules[FMath::Clamp(int32(Sound), 0, int32(ESRSound::Count) - 1)].Volume;
}

UAudioComponent* USRAudioSubsystem::PlayLoopAt(ESRSound Sound, const FVector& Location, float VolumeScale, float FadeIn)
{
	USoundBase* S = GetSound(Sound);
	const int32 I = int32(Sound);
	if (!S || !IsInRange(Sound, Location)) { return nullptr; }
	int32 Running = 0;
	for (const TWeakObjectPtr<UAudioComponent>& C : Loops) { Running += (C.IsValid() && C->Sound && C->IsPlaying() && Variants[I].Contains(C->Sound.Get())) ? 1 : 0; }
	if (Running >= FMath::RoundToInt(Rules[I].MaxLoad)) { return nullptr; }
	const float Vol = BaseVolume(Sound) * VolumeScale;
	UAudioComponent* C = UGameplayStatics::SpawnSoundAtLocation(this, S, Location, FRotator::ZeroRotator, FadeIn > 0.f ? 0.f : Vol, 1.f,
		FMath::FRandRange(0.f, 6.f), Attenuations[I], nullptr, true);
	if (C && FadeIn > 0.f) { C->FadeIn(FadeIn, Vol, FMath::FRandRange(0.f, 6.f)); }
	if (C) { Loops.Add(C); }
	return C;
}

void USRAudioSubsystem::PlayAt(ESRSound Sound, const FVector& Location, float VolumeScale, float PitchScale)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	// beyond its range it would be silent anyway (the falloff reaches zero there): do not spend a voice on it
	if (!IsInRange(Sound, Location)) { return; }
	USoundBase* S = GetSound(Sound);
	if (!S || !Allow(Sound)) { return; }
	const FSoundRule& R = Rules[int32(Sound)];
	const float Vol = F.MasterVolume * F.EffectsVolume * R.Volume * VolumeScale;
	const float Pitch = PitchScale * (1.f + FMath::FRandRange(-R.PitchJitter, R.PitchJitter));
	if (R.Range <= 0.f) { UGameplayStatics::PlaySound2D(this, S, Vol, Pitch); return; }
	UGameplayStatics::PlaySoundAtLocation(this, S, Location, FRotator::ZeroRotator, Vol, Pitch, 0.f, Attenuations[int32(Sound)]);
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
