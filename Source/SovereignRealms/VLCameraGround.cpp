#include "VLCameraGround.h"
#include "SovereignRealms.h"
#include "VLGrid.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Pawn.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"

namespace
{
	TAutoConsoleVariable<int32> CVarCamGround(TEXT("vl.Cam.Ground"), 1, TEXT("1: the cameras are kept out of the ground (lifted over the terrain under them). 0: as before, they go where the view puts them"));
	TAutoConsoleVariable<float> CVarCamClearance(TEXT("vl.Cam.Clearance"), 150.f, TEXT("the overview camera stays this many cm over the ground under it (the hero camera: UVLHeroBoom::GroundClearance)"));
	TAutoConsoleVariable<int32> CVarCamOverhang(TEXT("vl.Cam.Overhang"), 1, TEXT("1: a camera may go under terrain that hangs over open air (an arch, an overhang). 0: it stays over the top of the terrain everywhere"));
	TAutoConsoleVariable<int32> CVarCamLog(TEXT("vl.Cam.Log"), 0, TEXT("1: log, every half second, a camera that is being held up over the ground"));

	constexpr float NoFloor = -1.e9f;
}

UVLCameraGround* UVLCameraGround::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<UVLCameraGround>() : nullptr;
}

bool UVLCameraGround::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

float UVLCameraGround::OverviewClearance()
{
	return FMath::Clamp(CVarCamClearance.GetValueOnGameThread(), 20.f, 2000.f);
}

bool UVLCameraGround::IsActive()
{
	return CVarCamGround.GetValueOnGameThread() != 0 && Collect();
}

bool UVLCameraGround::Collect()
{
	if (Pieces.Num() > 0)
	{
		return true;
	}
	UWorld* World = GetWorld();
	if (!World || World->GetRealTimeSeconds() < NextCollect)
	{
		return false;
	}
	NextCollect = World->GetRealTimeSeconds() + 1.0;        // (a level with no ground: asked again once a second, not every frame)
	Bounds = FBox(ForceInit);
	// the ground as the path grid knows it (UVLGrid::Build)
	for (TActorIterator<AStaticMeshActor> It(World); It; ++It)
	{
		UStaticMeshComponent* Comp = It->GetStaticMeshComponent();
		const UStaticMesh* Mesh = Comp ? Comp->GetStaticMesh() : nullptr;
		if (!Mesh || It->ActorHasTag(TEXT("Water")) || It->ActorHasTag(TEXT("Backdrop")))
		{
			continue;
		}
		const FString Name = Mesh->GetName();
		if (It->ActorHasTag(TEXT("Ground")) || Name.StartsWith(TEXT("SM_Terrain")) || Name.StartsWith(TEXT("SM_Flat_")))
		{
			FPiece& Piece = Pieces.AddDefaulted_GetRef();
			Piece.Comp = Comp;
			Piece.Box = Comp->Bounds.GetBox();
			Bounds += Piece.Box;
		}
	}
	if (Pieces.Num() > 0)
	{
		UE_LOG(LogSovereignRealms, Log, TEXT("camera ground: %d piece(s) of terrain, %.0f x %.0f m, heights %.1f to %.1f m; the cameras stay %.0f cm (overview) over it"),
			Pieces.Num(), Bounds.GetSize().X / 100.0, Bounds.GetSize().Y / 100.0, Bounds.Min.Z / 100.0, Bounds.Max.Z / 100.0, OverviewClearance());
	}
	return Pieces.Num() > 0;
}

bool UVLCameraGround::Trace(const FVector2D& At, float FromZ, float ToZ, FHitResult& Out)
{
	static const FName TraceTag(TEXT("VLCameraGround"));
	FCollisionQueryParams Params(TraceTag, true);
	const float Lo = FMath::Min(FromZ, ToZ), Hi = FMath::Max(FromZ, ToZ);
	bool bHit = false;
	float Best = 0.f;
	for (int32 i = Pieces.Num() - 1; i >= 0; --i)
	{
		const FPiece& Piece = Pieces[i];
		if (At.X < Piece.Box.Min.X || At.X > Piece.Box.Max.X || At.Y < Piece.Box.Min.Y || At.Y > Piece.Box.Max.Y || Hi < Piece.Box.Min.Z || Lo > Piece.Box.Max.Z)
		{
			continue;
		}
		UStaticMeshComponent* Comp = Piece.Comp.Get();
		if (!Comp)
		{
			Pieces.RemoveAtSwap(i);         // (gone with its level)
			continue;
		}
		FHitResult Hit;
		if (Comp->LineTraceComponent(Hit, FVector(At.X, At.Y, FromZ), FVector(At.X, At.Y, ToZ), Params) && !Hit.bStartPenetrating)
		{
			const float Along = FMath::Abs(float(Hit.ImpactPoint.Z) - FromZ);
			if (!bHit || Along < Best)
			{
				bHit = true;
				Best = Along;
				Out = Hit;
			}
		}
	}
	return bHit;
}

bool UVLCameraGround::TopAt(const FVector2D& At, float& OutZ)
{
	FHitResult Hit;
	if (!Collect() || !Trace(At, Bounds.Max.Z + 50.f, Bounds.Min.Z - 50.f, Hit))
	{
		return false;
	}
	OutZ = Hit.ImpactPoint.Z;
	return true;
}

bool UVLCameraGround::SurfaceAt(const FVector2D& At, float& OutZ, float* OutTerrain, float* OutWater)
{
	if (!Collect())
	{
		return false;
	}
	float Top = 0.f;
	if (!TopAt(At, Top))
	{
		// beyond the terrain's edge (or over a gap in it): the edge's height
		const FVector2D In(FMath::Clamp(At.X, Bounds.Min.X + 30.f, Bounds.Max.X - 30.f), FMath::Clamp(At.Y, Bounds.Min.Y + 30.f, Bounds.Max.Y - 30.f));
		if (In.Equals(At, 0.5f) || !TopAt(In, Top))
		{
			return false;
		}
	}
	float Water = NoFloor;
	if (const UVLGrid* Grid = UVLGrid::Get(this); Grid && Grid->IsBuilt())
	{
		Water = Grid->WaterLevelAt(FVector(At.X, At.Y, 0.f));
	}
	if (OutTerrain)
	{
		*OutTerrain = Top;
	}
	if (OutWater)
	{
		*OutWater = Water;
	}
	OutZ = FMath::Max(Top, Water);
	return true;
}

bool UVLCameraGround::FloorAt(const FVector& Eye, float Clearance, float& OutZ)
{
	const FVector2D At(Eye);
	float Floor = 0.f, Top = 0.f, Water = NoFloor;
	if (!SurfaceAt(At, Floor, &Top, &Water))
	{
		return false;
	}
	if (Eye.Z < Top - 100.f && CVarCamOverhang.GetValueOnGameThread() != 0)
	{
		// Lower than the top of the terrain here: in the ground, or in open air under ground that hangs over it (an
		// arch, an overhang, a cave)? The terrain's surfaces are counted from its top down (a trace meets them from
		// either side). None between the top and the eye: the eye is in the ground itself, and the floor stays the
		// top. One: that is the underside of what hangs over, and the next one down is the floor of the place (the eye
		// may be over it or have sunk into it). A place too low for the camera is no place.
		FHitResult Under, Low;
		if (Trace(At, Top - 2.f, float(Eye.Z), Under)
			&& Trace(At, float(Under.ImpactPoint.Z) - 2.f, Bounds.Min.Z - 50.f, Low)
			&& Under.ImpactPoint.Z - Low.ImpactPoint.Z >= Clearance + 80.f)
		{
			Floor = FMath::Max(float(Low.ImpactPoint.Z), Water);
		}
	}
	OutZ = Floor;
	return true;
}

float UVLCameraGround::KeepAbove(FVector& Eye, FVLCameraFloor& State, float DeltaSeconds, bool bSnap, float Clearance, const TCHAR* Who)
{
	if (!IsActive())
	{
		State.bValid = false;
		return 0.f;
	}
	// higher than everything on the map: nothing to ask
	if (Eye.Z > Bounds.Max.Z + Clearance + 20.f)
	{
		State.bValid = false;
		return 0.f;
	}
	float Here = NoFloor;
	if (!FloorAt(Eye, Clearance, Here))
	{
		State.bValid = false;
		return 0.f;
	}
	const bool bFresh = bSnap || !State.bValid;
	float Target = Here;
	if (!bFresh && DeltaSeconds > 1.e-4f)
	{
		// where the eye is going: a hillside is climbed before it is met
		FVector2D Way = FVector2D(Eye - State.LastEye) / DeltaSeconds * LookAheadSeconds;
		const float Len = Way.Size();
		if (Len > 25.f)
		{
			Way *= FMath::Min(Len, LookAheadMax) / Len;
			float Ahead = NoFloor;
			if (FloorAt(FVector(Eye.X + Way.X, Eye.Y + Way.Y, Eye.Z), Clearance, Ahead))
			{
				Target = FMath::Max(Target, Ahead);
			}
		}
	}
	State.Soft = bFresh ? Target : FMath::FInterpTo(State.Soft, Target, DeltaSeconds, Target > State.Soft ? RiseRate : FallRate);
	// (never so far behind the ground itself that the eye would be within the hard clearance of it)
	State.Soft = FMath::Max(State.Soft, Here - Clearance * (1.f - FMath::Clamp(HardShare, 0.f, 1.f)));
	State.LastEye = Eye;
	State.bValid = true;
	const float Lift = State.Soft + Clearance - float(Eye.Z);
	if (Lift <= 0.f)
	{
		return 0.f;
	}
	Eye.Z += Lift;
	if (CVarCamLog.GetValueOnGameThread() != 0)
	{
		if (const UWorld* World = GetWorld(); World && World->GetRealTimeSeconds() >= NextLog)
		{
			NextLog = World->GetRealTimeSeconds() + 0.5;
			UE_LOG(LogSovereignRealms, Log, TEXT("camera ground: the %s camera at %.0f %.0f lifted %.0f cm to %.0f (the ground there %.0f, smoothed %.0f)"),
				Who, Eye.X, Eye.Y, Lift, Eye.Z, Here, State.Soft);
		}
	}
	return Lift;
}

void UVLHeroBoom::UpdateDesiredArmLocation(bool bDoTrace, bool bDoLocationLag, bool bDoRotationLag, float DeltaTime)
{
	Super::UpdateDesiredArmLocation(bDoTrace, bDoLocationLag, bDoRotationLag, DeltaTime);
	UVLCameraGround* Ground = UVLCameraGround::Get(this);
	// (only while the view is this unit's own: behind the overview the arm goes on following him, unasked)
	const APawn* Pawn = Cast<APawn>(GetOwner());
	const APlayerController* PC = Pawn ? Cast<APlayerController>(Pawn->GetController()) : nullptr;
	if (!Ground || !PC || PC->GetViewTarget() != Pawn)
	{
		Floor.bValid = false;
		return;
	}
	const FTransform Socket = FTransform(RelativeSocketRotation, RelativeSocketLocation) * GetComponentTransform();
	FVector Eye = Socket.GetLocation();
	const float Lift = Ground->KeepAbove(Eye, Floor, DeltaTime, false, GroundClearance, TEXT("hero"));
	if (Lift <= 0.f)
	{
		return;
	}
	// lifted: it looks at what the arm looked at (the unit stays where it was in the picture)
	const FVector Aim = Socket.GetLocation() + Socket.GetRotation().GetForwardVector() * FMath::Max(TargetArmLength, 100.f);
	const FTransform Rel = FTransform((Aim - Eye).ToOrientationQuat(), Eye).GetRelativeTransform(GetComponentTransform());
	RelativeSocketLocation = Rel.GetLocation();
	RelativeSocketRotation = Rel.GetRotation();
	UpdateChildTransforms();
}
