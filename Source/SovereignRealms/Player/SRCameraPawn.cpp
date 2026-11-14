// Copyright Sovereign Realms.

#include "Player/SRCameraPawn.h"
#include "Battle/SRBattleSubsystem.h"
#include "Common/SRFeelSettings.h"
#include "Camera/CameraComponent.h"
#include "Player/SRPlayerController.h"

namespace
{
	/** Frame-rate independent smoothing factor for a given time constant. */
	float SmoothAlpha(float Dt, float TimeConstant)
	{
		return 1.f - FMath::Exp(-Dt / FMath::Max(TimeConstant, 0.0001f));
	}

	float DistanceForZoom(const USRFeelSettings& F, float Zoom01)
	{
		// Geometric interpolation: every wheel notch changes apparent size by the same ratio.
		return F.ZoomDistanceMin * FMath::Pow(F.ZoomDistanceMax / F.ZoomDistanceMin, FMath::Clamp(Zoom01, 0.f, 1.f));
	}
}

ASRCameraPawn::ASRCameraPawn()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickGroup = TG_PostPhysics;

	SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(GetRootComponent());
	Camera->SetUsingAbsoluteLocation(true);
	Camera->SetUsingAbsoluteRotation(true);

	bUseControllerRotationYaw = false;
	bUseControllerRotationPitch = false;
}

void ASRCameraPawn::BeginPlay()
{
	Super::BeginPlay();
	const USRFeelSettings& F = USRFeelSettings::Get();
	Zoom = ZoomTarget = F.ZoomDefault;
	Focus = F.PlayerStart;
	ApplyView(0.f);
}

float ASRCameraPawn::GetZoomDistance() const
{
	return DistanceForZoom(USRFeelSettings::Get(), Zoom);
}

void ASRCameraPawn::AddZoomInput(float Notches, const FVector* CursorGround)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const float Before = ZoomTarget;
	ZoomTarget = FMath::Clamp(ZoomTarget - Notches * F.ZoomStep, 0.f, 1.f);

	// Zooming in drifts toward what the cursor is pointing at, so you zoom "into" a spot.
	if (CursorGround && Notches > 0.f && ZoomTarget < Before && F.ZoomToCursorStrength > 0.f)
	{
		const FVector2D Base = bRecentering ? RecenterGoal : Focus;
		RecenterGoal = FMath::Lerp(Base, FVector2D(CursorGround->X, CursorGround->Y), F.ZoomToCursorStrength * FMath::Min(Notches, 1.f));
		bRecentering = true;
	}
}

void ASRCameraPawn::FocusOn(const FVector2D& WorldXY, bool bSnap)
{
	if (bSnap)
	{
		Focus = WorldXY;
		PanVelocity = FVector2D::ZeroVector;
		bRecentering = false;
		float GroundZ = FocusZ;
		if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this))
		{
			if (Battle->SampleGround(Focus, 20000.f, GroundZ)) { FocusZ = GroundZ; }
		}
		ApplyView(0.f);
	}
	else
	{
		RecenterGoal = WorldXY;
		bRecentering = true;
	}
}

void ASRCameraPawn::SetZoom(float Zoom01, bool bSnap)
{
	ZoomTarget = FMath::Clamp(Zoom01, 0.f, 1.f);
	if (bSnap) { Zoom = ZoomTarget; ApplyView(0.f); }
}

void ASRCameraPawn::AddTrauma(float Amount)
{
	Trauma = FMath::Clamp(Trauma + Amount, 0.f, 1.f);
}

bool ASRCameraPawn::CursorOnFocusPlane(FVector& OutPoint) const
{
	const ASRPlayerController* PC = Cast<ASRPlayerController>(GetController());
	FVector Origin, Dir;
	if (!PC || !PC->GetCursorRay(Origin, Dir) || FMath::Abs(Dir.Z) < KINDA_SMALL_NUMBER) { return false; }
	OutPoint = Origin + Dir * ((FocusZ - Origin.Z) / Dir.Z);
	return true;
}

void ASRCameraPawn::BeginDragPan()
{
	bDragging = CursorOnFocusPlane(DragAnchor);
	if (bDragging)
	{
		bRecentering = false;
		PanVelocity = FVector2D::ZeroVector;
	}
}

void ASRCameraPawn::EndDragPan()
{
	bDragging = false; // PanVelocity keeps the last drag speed, so a flick glides to a stop
}

void ASRCameraPawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const float Dt = FMath::Min(DeltaSeconds, 0.1f);
	const USRFeelSettings& F = USRFeelSettings::Get();

	Zoom = FMath::Lerp(Zoom, ZoomTarget, SmoothAlpha(Dt, F.ZoomSmoothTime));
	const float Distance = DistanceForZoom(F, Zoom);

	const float YawRad = FMath::DegreesToRadians(F.CameraYaw);
	const FVector2D Fwd(FMath::Cos(YawRad), FMath::Sin(YawRad));
	const FVector2D Right(-Fwd.Y, Fwd.X);

	FVector CursorPoint;
	if (bDragging && CursorOnFocusPlane(CursorPoint))
	{
		// Keep the grabbed ground point under the cursor: 1:1, no smoothing, like dragging a map.
		const FVector2D Delta(DragAnchor.X - CursorPoint.X, DragAnchor.Y - CursorPoint.Y);
		Focus += Delta;
		if (Dt > KINDA_SMALL_NUMBER)
		{
			PanVelocity = FMath::Lerp(PanVelocity, Delta / Dt, 0.5f).GetClampedToMaxSize(F.PanSpeed * 3.f);
		}
	}
	else
	{
		FVector2D Input = PanInput;
		if (Input.SizeSquared() > 1.f) { Input.Normalize(); }
		const bool bHasInput = !Input.IsNearlyZero();
		if (bHasInput) { bRecentering = false; } // the player always wins over an automatic glide

		// Pan faster when zoomed out so the screen-space speed feels constant.
		const float ZoomScale = Distance / DistanceForZoom(F, F.ZoomDefault);
		const FVector2D TargetVelocity = (Fwd * Input.Y + Right * Input.X) * F.PanSpeed * ZoomScale;
		PanVelocity = FMath::Lerp(PanVelocity, TargetVelocity, SmoothAlpha(Dt, bHasInput ? F.PanAccelTime : F.PanDecelTime));
		Focus += PanVelocity * Dt;

		if (bRecentering)
		{
			Focus = FMath::Lerp(Focus, RecenterGoal, SmoothAlpha(Dt, F.RecenterSmoothTime));
			if (FVector2D::DistSquared(Focus, RecenterGoal) < 4.f) { bRecentering = false; }
		}
	}

	// Map bounds: stop dead at the edge rather than pushing against it.
	const FVector2D Clamped(FMath::Clamp(Focus.X, -F.MapHalfExtent.X, F.MapHalfExtent.X), FMath::Clamp(Focus.Y, -F.MapHalfExtent.Y, F.MapHalfExtent.Y));
	if (Clamped.X != Focus.X) { PanVelocity.X = 0.f; }
	if (Clamped.Y != Focus.Y) { PanVelocity.Y = 0.f; }
	Focus = Clamped;

	// Ride the terrain so the framing holds on hills and terraces.
	if (const USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this))
	{
		float GroundZ = FocusZ;
		if (Battle->SampleGround(Focus, FocusZ + 3000.f, GroundZ))
		{
			FocusZ = FMath::Lerp(FocusZ, GroundZ, SmoothAlpha(Dt, 0.25f));
		}
	}

	Trauma = FMath::Max(0.f, Trauma - F.ShakeDecay * Dt);
	ShakeClock += Dt;
	ApplyView(Dt);
}

void ASRCameraPawn::ApplyView(float DeltaSeconds)
{
	const USRFeelSettings& F = USRFeelSettings::Get();
	const float Distance = DistanceForZoom(F, Zoom);
	// Tilt: lower, more side-on when close; steeper, more map-like when far.
	const FRotator ViewRot(FMath::Lerp(F.PitchZoomedIn, F.PitchZoomedOut, Zoom), F.CameraYaw, 0.f);
	const FVector FocusPoint(Focus.X, Focus.Y, FocusZ);
	FVector CameraPos = FocusPoint - ViewRot.Vector() * Distance;

	if (F.bCameraShake && Trauma > 0.f)
	{
		// Trauma squared: small knocks are barely there, big ones punch. Screen-plane offset only, no rotation.
		const float Amount = Trauma * Trauma * F.ShakeMaxOffset;
		const float Phase = ShakeClock * F.ShakeFrequency;
		const FRotationMatrix Axes(ViewRot);
		CameraPos += Axes.GetUnitAxis(EAxis::Y) * FMath::PerlinNoise1D(Phase) * Amount * 2.f;
		CameraPos += Axes.GetUnitAxis(EAxis::Z) * FMath::PerlinNoise1D(Phase + 57.3f) * Amount * 2.f;
	}

	SetActorLocation(FocusPoint);
	Camera->SetWorldLocationAndRotation(CameraPos, ViewRot);
	Camera->SetFieldOfView(F.CameraFOV);
	Camera->PostProcessSettings.bOverride_MotionBlurAmount = F.bDisableMotionBlur;
	Camera->PostProcessSettings.MotionBlurAmount = 0.f;
}
