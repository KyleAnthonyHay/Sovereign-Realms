// The unit rig's pose buffer and its late write to the components (optimisation pass A1-A4, A6): see VLKing.h,
// "the rig's pose". AVLKing::Animate / PoseFigure (VLKing.cpp) and the components that pose parts of a figure
// (UVLArcherCombat, UVLSpy) write joint transforms here; nothing moves until RigLateUpdate.
#include "VLKing.h"
#include "SovereignRealms.h"
#include "VLCharacterData.h"
#include "VLHUD.h"
#include "VLCameraGround.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "ConvexVolume.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "HAL/IConsoleManager.h"
#include "Misc/App.h"
#include "SceneView.h"
#include "UnrealClient.h"

namespace
{
	TAutoConsoleVariable<int32> CVarRigBatch(TEXT("vl.Opt.RigBatch"), 1,
		TEXT("1: unit figures are posed in a buffer and written to their components once a frame. 0: the old way, every joint write moves the components at once (for comparing)"));
	TAutoConsoleVariable<int32> CVarRigLOD(TEXT("vl.Opt.RigLOD"), 1,
		TEXT("1: units out of view are not posed, far ones at a lower rate, and a part that moved less than vl.Opt.RigPixelError is not sent to the renderer. 0: every unit, every frame"));
	TAutoConsoleVariable<float> CVarRigPixelError(TEXT("vl.Opt.RigPixelError"), 0.25f,
		TEXT("a unit's part is given to the renderer again once it has moved this many pixels (the player's unit and the King: always)"));
	TAutoConsoleVariable<float> CVarRigFarDist(TEXT("vl.Opt.RigFarDist"), 7500.f,
		TEXT("cm from the camera beyond which units are posed 30 times a second (20 beyond twice that, the cape holding its shape); where the HUD's pips begin"));
	TAutoConsoleVariable<float> CVarRigCullMargin(TEXT("vl.Opt.RigCullMargin"), 900.f,
		TEXT("cm: a unit this far outside the view is still posed (its shadow may reach in)"));
	TAutoConsoleVariable<int32> CVarUnitDepth(TEXT("vl.Opt.UnitDepth"), 1,
		TEXT("1: units write custom depth (the silhouette) only in a match and within vl.Opt.UnitDepthFar of the camera. 0: always"));
	TAutoConsoleVariable<float> CVarUnitDepthFar(TEXT("vl.Opt.UnitDepthFar"), 40000.f, TEXT("cm from the camera beyond which a unit writes no custom depth (back on at 0.9 of it)"));
	TAutoConsoleVariable<int32> CVarUnitGI(TEXT("vl.Opt.UnitGI"), 0, TEXT("1: unit parts are in Lumen's scene and the indirect lighting cache, as before"));
	TAutoConsoleVariable<int32> CVarRigStats(TEXT("vl.RigStats"), 0, TEXT("1: log every 2 s how many units were posed and written, and how many parts were given to the renderer, per frame"));

	TArray<AVLKing*> GRigUnits;
	FDelegateHandle GRigLateHandle;
	int32 GRigSerial = 0;

	// (vl.RigStats) since the last line
	int32 GStatFrames = 0, GStatUnits = 0, GStatPosed = 0, GStatFlushed = 0, GStatSent = 0;
	double GStatLast = 0.0;
	bool GStatOn = false;
	uint64 GStatPoseCycles = 0, GStatFlushCycles = 0, GStatLateCycles = 0;

	/** (vl.RigStats) the time spent in a scope, added up. */
	struct FRigTimer
	{
		uint64& Sum;
		const uint64 Start;
		explicit FRigTimer(uint64& InSum) : Sum(InSum), Start(GStatOn ? FPlatformTime::Cycles64() : 0) {}
		~FRigTimer()
		{
			if (Start)
			{
				Sum += FPlatformTime::Cycles64() - Start;
			}
		}
	};

	/** True if a part at B has moved more than the tolerance (squared, cm) from A: its place, and its turn at Reach. */
	bool RigMoved(const FTransform& A, const FTransform& B, double Reach, double TolSq)
	{
		const double D2 = FVector::DistSquared(A.GetLocation(), B.GetLocation());
		const double Dot = A.GetRotation() | B.GetRotation();
		const double Ang2 = 4.0 * FMath::Max(0.0, 1.0 - Dot * Dot);          // the angle between them, squared (small angles)
		const double S2 = (A.GetScale3D() - B.GetScale3D()).SizeSquared();
		return 2.0 * (D2 + (Ang2 + S2) * Reach * Reach) > TolSq;             // ((d + r a)^2 <= 2 (d^2 + r^2 a^2))
	}
}

bool VLRigLodOn()
{
	return CVarRigLOD.GetValueOnGameThread() != 0;
}

bool VLUnitGI()
{
	return CVarUnitGI.GetValueOnGameThread() != 0;
}

/** This frame's view, for every unit. */
struct FVLRigView
{
	bool bBatch = true;
	bool bLod = true;
	bool bValid = false;        // there is a camera
	FConvexVolume Frustum;
	FVector Eye = FVector::ZeroVector;
	double CmPerPx = 0.0;       // at 1 cm from the eye
	double PixelError = 0.25;
	double FarDist = 7500.0;
	double Margin = 900.0;
	float RealDt = 0.016f;
	float Dt = 0.016f;
	bool bDepthGate = true;
	bool bUnitGI = false;
	bool bTitle = false;
	double DepthFar = 40000.0;
};

// ------------------------------------------------------------------------------------------------ the buffer

int32 AVLKing::RigFind(FName Name) const
{
	const int32* Found = RigIndex.Find(Name);
	return Found ? *Found : INDEX_NONE;
}

const FTransform& AVLKing::RigLocal(int32 Node, uint64& OutStamp) const
{
	if (!RigNodes.IsValidIndex(Node))
	{
		OutStamp = FigureStamp;
		return FigureLocal;
	}
	const FRigNode& N = RigNodes[Node];
	uint64 Above = 0;
	const FTransform& P = RigLocal(N.Parent, Above);
	if (N.LocalStamp <= N.RelStamp || N.LocalStamp <= Above)
	{
		N.Local = FTransform(N.RelRot, N.RelLoc, N.RelScale) * P;
		N.LocalStamp = ++RigClock;
	}
	OutStamp = N.LocalStamp;
	return N.Local;
}

FTransform AVLKing::RigWorld(int32 Node) const
{
	if (bRigLegacy)
	{
		return RigNodes.IsValidIndex(Node) ? RigNodes[Node].Joint->GetComponentTransform() : Figure->GetComponentTransform();
	}
	uint64 Stamp = 0;
	return RigLocal(Node, Stamp) * GetCapsuleComponent()->GetComponentTransform();
}

FQuat AVLKing::RigRelRot(int32 Node) const
{
	if (!RigNodes.IsValidIndex(Node))
	{
		return FQuat::Identity;
	}
	return bRigLegacy ? RigNodes[Node].Joint->GetRelativeRotation().Quaternion() : RigNodes[Node].RelRot;
}

FRotator AVLKing::RigRelRotator(int32 Node) const
{
	if (!RigNodes.IsValidIndex(Node))
	{
		return FRotator::ZeroRotator;
	}
	return bRigLegacy ? RigNodes[Node].Joint->GetRelativeRotation() : RigNodes[Node].RelRot.Rotator();
}

FVector AVLKing::RigRelLoc(int32 Node) const
{
	if (!RigNodes.IsValidIndex(Node))
	{
		return FVector::ZeroVector;
	}
	return bRigLegacy ? RigNodes[Node].Joint->GetRelativeLocation() : RigNodes[Node].RelLoc;
}

FVector AVLKing::RigRelScale(int32 Node) const
{
	if (!RigNodes.IsValidIndex(Node))
	{
		return FVector::OneVector;
	}
	return bRigLegacy ? RigNodes[Node].Joint->GetRelativeScale3D() : RigNodes[Node].RelScale;
}

void AVLKing::RigSetRelRot(int32 Node, const FQuat& Q)
{
	if (!RigNodes.IsValidIndex(Node))
	{
		return;
	}
	FRigNode& N = RigNodes[Node];
	if (bRigLegacy)
	{
		N.Joint->SetRelativeRotation(Q);
		return;
	}
	N.RelRot = Q;
	N.RelStamp = ++RigClock;
	bRigDirty = true;
}

void AVLKing::RigSetRelScale(int32 Node, const FVector& Scale)
{
	if (!RigNodes.IsValidIndex(Node))
	{
		return;
	}
	FRigNode& N = RigNodes[Node];
	if (bRigLegacy)
	{
		N.Joint->SetRelativeScale3D(Scale);
		return;
	}
	N.RelScale = Scale;
	N.RelStamp = ++RigClock;
	bRigDirty = true;
}

void AVLKing::RigSetWorldRot(int32 Node, const FQuat& Q)
{
	if (!RigNodes.IsValidIndex(Node))
	{
		return;
	}
	FRigNode& N = RigNodes[Node];
	if (bRigLegacy)
	{
		N.Joint->SetWorldRotation(Q);
		return;
	}
	// (as USceneComponent::SetWorldRotation: the parent's turn taken out)
	uint64 Stamp = 0;
	const FQuat Above = GetCapsuleComponent()->GetComponentQuat() * RigLocal(N.Parent, Stamp).GetRotation();
	N.RelRot = Above.Inverse() * Q;
	N.RelStamp = ++RigClock;
	bRigDirty = true;
}

void AVLKing::RigSetWorldLocRot(int32 Node, const FVector& Location, const FQuat& Q)
{
	if (!RigNodes.IsValidIndex(Node))
	{
		return;
	}
	FRigNode& N = RigNodes[Node];
	if (bRigLegacy)
	{
		N.Joint->SetWorldLocationAndRotation(Location, Q);
		return;
	}
	const FTransform Above = RigWorld(N.Parent);
	N.RelLoc = Above.InverseTransformPosition(Location);
	N.RelRot = Above.GetRotation().Inverse() * Q;
	N.RelStamp = ++RigClock;
	bRigDirty = true;
}

void AVLKing::RigSetFigure(const FVector& Location, const FQuat& Q)
{
	FigureLocal = FTransform(Q, Location);
	FigureStamp = ++RigClock;
	bRigDirty = true;
	if (bRigLegacy)
	{
		Figure->SetRelativeLocationAndRotation(Location, Q);
	}
}

UStaticMeshComponent* AVLKing::RigMesh(int32 Node) const
{
	return RigNodes.IsValidIndex(Node) ? RigNodes[Node].Mesh : nullptr;
}

FQuat AVLKing::RigMeshRot(int32 Node) const
{
	return RigNodes.IsValidIndex(Node) ? RigNodes[Node].MeshRot : FQuat::Identity;
}

void AVLKing::RigSetMeshRot(int32 Node, const FQuat& Q)
{
	if (!RigNodes.IsValidIndex(Node) || !RigNodes[Node].Mesh)
	{
		return;
	}
	RigNodes[Node].MeshRot = Q;
	RigNodes[Node].Mesh->SetRelativeRotation(Q);
	bRigDirty = true;
	bRigForce = true;
}

void AVLKing::AddRigPoser(UActorComponent* PoserOwner, TFunction<void(AVLKing*)> Pose)
{
	FRigPoser& P = RigPosers.AddDefaulted_GetRef();
	P.Owner = PoserOwner;
	P.Pose = MoveTemp(Pose);
}

void AVLKing::RigBuild()
{
	// (BuildFigure has made the nodes, in the order of the parts)
	FigureLocal = FTransform(Figure->GetRelativeRotation().Quaternion(), Figure->GetRelativeLocation());
	FigureStamp = ++RigClock;
	for (FRigNode& N : RigNodes)
	{
		N.WrittenLoc = N.RelLoc;
		N.WrittenRot = N.RelRot;
		N.WrittenScale = N.RelScale;
		N.Children = N.Joint->GetNumChildrenComponents();
		if (N.Mesh && N.Mesh->GetStaticMesh())
		{
			const FBoxSphereBounds B = N.Mesh->GetStaticMesh()->GetBounds();
			N.Reach = B.Origin.Size() + B.SphereRadius;
		}
	}
	bRigLegacy = true;          // (as built: everything hangs from the capsule)
	bRigForce = true;
	RigSerial = ++GRigSerial;
	RigSetLegacy(CVarRigBatch.GetValueOnGameThread() == 0);
}

void AVLKing::RigSyncFromComponents()
{
	FigureLocal = FTransform(Figure->GetRelativeRotation().Quaternion(), Figure->GetRelativeLocation());
	FigureStamp = ++RigClock;
	for (FRigNode& N : RigNodes)
	{
		N.RelLoc = N.WrittenLoc = N.Joint->GetRelativeLocation();
		N.RelRot = N.WrittenRot = N.Joint->GetRelativeRotation().Quaternion();
		N.RelScale = N.WrittenScale = N.Joint->GetRelativeScale3D();
		N.RelStamp = ++RigClock;
		if (N.Mesh)
		{
			N.MeshRot = N.Mesh->GetRelativeRotation().Quaternion();
		}
	}
}

void AVLKing::RigSetLegacy(bool bLegacy)
{
	if (bLegacy == bRigLegacy || !Figure)
	{
		return;
	}
	if (bLegacy)
	{
		// the components as the buffer has them, then the figure back on the capsule
		RigFlush(0.0, true);
		bRigLegacy = true;
		Figure->SetRelativeLocation_Direct(FigureLocal.GetLocation());
		Figure->SetRelativeRotation_Direct(FigureLocal.Rotator());
		Figure->SetAbsolute(false, false, false);
		Figure->UpdateComponentToWorld();
	}
	else
	{
		// The figure no longer follows the capsule by itself (a capsule move then touches none of its ~70 parts): it
		// is placed with the rest of the rig, once a frame.
		RigSyncFromComponents();
		const FTransform World = FigureLocal * GetCapsuleComponent()->GetComponentTransform();
		Figure->SetRelativeLocation_Direct(World.GetLocation());
		Figure->SetRelativeRotation_Direct(World.Rotator());
		Figure->SetAbsolute(true, true, true);
		bRigLegacy = false;
		bRigForce = true;
		bRigDirty = true;
		RigFlush(0.0, true);
	}
}

void AVLKing::RigScanExtras()
{
	RigExtras.Reset();
	for (FRigNode& N : RigNodes)
	{
		N.Children = N.Joint->GetNumChildrenComponents();
		for (USceneComponent* Child : N.Joint->GetAttachChildren())
		{
			if (!Child || Child == N.Mesh || RigNodes.ContainsByPredicate([Child](const FRigNode& Other) { return Other.Joint == Child; }))
			{
				continue;
			}
			RigExtras.Add({ Child });
		}
	}
}

void AVLKing::RigFlush(double Tolerance, bool bForce)
{
	if (bRigLegacy || !Figure)
	{
		return;
	}
	FRigTimer Timer(GStatFlushCycles);
	const FTransform& Root = GetCapsuleComponent()->GetComponentTransform();
	const double TolSq = FMath::Max(Tolerance * Tolerance, 1e-10);
	const FTransform FigureWorld = FigureLocal * Root;
	if (!Figure->GetComponentTransform().Equals(FigureWorld, 0.0))
	{
		Figure->SetRelativeLocation_Direct(FigureWorld.GetLocation());
		Figure->SetRelativeRotation_Direct(FigureWorld.Rotator());
		Figure->SetComponentToWorld(FigureWorld);
	}
	bool bRescan = false;
	int32 Sent = 0;
	for (int32 i = 0; i < RigNodes.Num(); ++i)
	{
		FRigNode& N = RigNodes[i];
		uint64 Stamp = 0;
		const FTransform World = RigLocal(i, Stamp) * Root;
		// the joint's own numbers kept true as well: whatever the engine works out from them is what was set here
		if (N.WrittenRot != N.RelRot)
		{
			N.Joint->SetRelativeRotation_Direct(N.RelRot.Rotator());
			N.WrittenRot = N.RelRot;
		}
		if (N.WrittenLoc != N.RelLoc)
		{
			N.Joint->SetRelativeLocation_Direct(N.RelLoc);
			N.WrittenLoc = N.RelLoc;
		}
		if (N.WrittenScale != N.RelScale)
		{
			N.Joint->SetRelativeScale3D_Direct(N.RelScale);
			N.WrittenScale = N.RelScale;
		}
		N.Joint->SetComponentToWorld(World);
		if (N.Mesh)
		{
			const FTransform MeshWorld = FTransform(N.MeshRot) * World;
			N.Mesh->SetComponentToWorld(MeshWorld);
			if (bForce || !N.bSent || RigMoved(MeshWorld, N.Sent, N.Reach, TolSq))
			{
				N.Mesh->UpdateBounds();
				N.Mesh->MarkRenderTransformDirty();
				N.Sent = MeshWorld;
				N.bSent = true;
				++Sent;
			}
		}
		bRescan |= N.Joint->GetNumChildrenComponents() != N.Children;
	}
	if (bRescan)
	{
		RigScanExtras();
	}
	for (const FRigExtra& Extra : RigExtras)
	{
		if (USceneComponent* C = Extra.Component.Get())
		{
			C->UpdateComponentToWorld();
		}
	}
	bRigDirty = false;
	bRigForce = false;
	bRigStale = false;
	RigFlushedAt = Root.GetLocation();
	++GStatFlushed;
	GStatSent += Sent;
}

void AVLKing::RigCompare(double& OutCm, double& OutDeg) const
{
	OutCm = OutDeg = 0.0;
	if (bRigLegacy || !Figure)
	{
		return;
	}
	const FTransform& Root = GetCapsuleComponent()->GetComponentTransform();
	for (int32 i = 0; i < RigNodes.Num(); ++i)
	{
		uint64 Stamp = 0;
		const FTransform Want = RigLocal(i, Stamp) * Root;
		const FTransform Have = RigNodes[i].Joint->GetComponentTransform();
		OutCm = FMath::Max(OutCm, FVector::Dist(Want.GetLocation(), Have.GetLocation()));
		OutDeg = FMath::Max(OutDeg, double(FMath::RadiansToDegrees(Want.GetRotation().AngularDistance(Have.GetRotation()))));
	}
}

void AVLKing::RigSelfCheck(double& OutCm, double& OutDeg)
{
	OutCm = OutDeg = 0.0;
	if (bRigLegacy || !Loaded || !Rig.Body || !Rig.Chest || bDead)
	{
		return;
	}
	auto PoseAll = [this]()
	{
		PoseFigure(0.f);        // (no time passes: the pose as it stands, nothing of the game moves on)
		for (const FRigPoser& P : RigPosers)
		{
			if (P.Owner.IsValid())
			{
				P.Pose(this);
			}
		}
	};
	PoseAll();
	TArray<FTransform> Buffered;
	for (int32 i = 0; i < RigNodes.Num(); ++i)
	{
		Buffered.Add(RigWorld(i));
	}
	RigSetLegacy(true);
	PoseAll();
	for (int32 i = 0; i < RigNodes.Num(); ++i)
	{
		const FTransform Old = RigNodes[i].Joint->GetComponentTransform();
		OutCm = FMath::Max(OutCm, FVector::Dist(Old.GetLocation(), Buffered[i].GetLocation()));
		OutDeg = FMath::Max(OutDeg, double(FMath::RadiansToDegrees(Old.GetRotation().AngularDistance(Buffered[i].GetRotation()))));
	}
	RigSetLegacy(false);
}

// ------------------------------------------------------------------------------------------------ posing, late

void AVLKing::PoseNow(bool bAtTick)
{
	if (!Loaded || !Rig.Body || !Rig.Chest)
	{
		return;
	}
	// A unit posed every frame moves on by that frame's time, as ever. One left out for a while (out of view) starts
	// its cloth and its wrist afresh from where the pose puts them: no leap from a long step.
	FRigTimer Timer(GStatPoseCycles);
	const bool bGap = !bAtTick && RigSincePose > 0.2f;
	const float AnimDt = bAtTick ? RigPoseDt : FMath::Min(RigPoseDt, 0.1f);
	if (bGap)
	{
		bRigResume = true;
		bCapeStarted = false;
	}
	PoseFigure(AnimDt);
	bRigResume = false;
	RigPoseDt = 0.f;
	RigSincePose = 0.f;
	bRigPosedThisFrame = true;
	bRigPosedAtTick = bAtTick;
	bRigDirty = true;
	++GStatPosed;
	// what else poses parts of it (the bow arm, the spyglass): a ticking component does so in its own tick, after this
	for (int32 i = RigPosers.Num() - 1; i >= 0; --i)
	{
		const UActorComponent* PoserOwner = RigPosers[i].Owner.Get();
		if (!PoserOwner)
		{
			RigPosers.RemoveAt(i);
		}
		else if (!bAtTick || !PoserOwner->IsComponentTickEnabled())
		{
			RigPosers[i].Pose(this);
		}
	}
}

void AVLKing::RigLate(const FVLRigView& View)
{
	const bool bPosed = bRigPosedThisFrame;
	bRigPosedThisFrame = false;
	if (!Loaded || !Figure)
	{
		return;
	}
	if (View.bBatch == bRigLegacy)
	{
		RigSetLegacy(!View.bBatch);
	}
	const FVector At = GetActorLocation();
	// ---- the silhouette's custom depth: not behind the title screen, not for units far from the camera (either side
	// alike: a foe in front of one of the player's still covers its outline). Only changed as a unit crosses the line.
	{
		bool bWant = true;
		if (View.bDepthGate)
		{
			if (View.bTitle)
			{
				bWant = false;
			}
			else if (View.bValid)
			{
				const double Far = bDepthOn ? View.DepthFar : View.DepthFar * 0.9;
				bWant = FVector::DistSquared(View.Eye, At) < Far * Far;
			}
		}
		if (bWant != bDepthOn)
		{
			UpdateCustomDepth(bWant);
		}
	}
	if (View.bUnitGI != bUnitGI)
	{
		// (vl.Opt.UnitGI changed: for comparing the two looks in one session)
		bUnitGI = View.bUnitGI;
		for (UStaticMeshComponent* PartMesh : Meshes)
		{
			if (PartMesh)
			{
				PartMesh->bAffectDynamicIndirectLighting = bUnitGI;
				PartMesh->IndirectLightingCacheQuality = bUnitGI ? ILCQ_Point : ILCQ_Off;
				PartMesh->MarkRenderStateDirty();
			}
		}
	}
	++GStatUnits;
	if (bRigLegacy || IsHidden())
	{
		return;
	}
	// ---- is it seen? (where it is, and where its parts were left if they were not moved with it)
	const bool bHero = !bTroop || IsPlayerControlled();
	const bool bLod = View.bLod && View.bValid && !bHero;
	if (bLod && !View.Frustum.IntersectSphere(At, View.Margin) && !(bRigStale && View.Frustum.IntersectSphere(RigFlushedAt, View.Margin)))
	{
		bRigStale = true;
		return;
	}
	double Tolerance = 0.0;
	bool bHoldCape = false;
	if (bLod)
	{
		const double Dist = FVector::Dist(View.Eye, At);
		const double CmPerPx = FMath::Max(Dist * View.CmPerPx, 1e-4);
		Tolerance = View.PixelError * CmPerPx;
		if (Dist > View.FarDist && !bRigStale && !bRigForce)
		{
			// far off: 30 times a second, 20 beyond twice as far; but never so seldom that it would be seen to hop
			// (no more than 3/4 of a pixel of its own movement between two poses)
			bHoldCape = Dist > 2.0 * View.FarDist;
			int32 Every = FMath::Clamp(FMath::RoundToInt32((bHoldCape ? 0.05f : 1.f / 30.f) / FMath::Max(View.RealDt, 0.001f)), 1, 4);
			const double StepPx = GetVelocity().Size() * View.Dt / CmPerPx;
			if (StepPx > 1e-3)
			{
				Every = FMath::Min(Every, 1 + int32(0.75 / StepPx));
			}
			if (Every > 1 && ((GFrameCounter + uint64(RigSerial)) % uint64(Every)) != 0)
			{
				return;
			}
		}
	}
	if (bHoldCape != bRigCapeHeld)
	{
		bRigCapeHeld = bHoldCape;
		bCapeStarted = bCapeStarted && bHoldCape;           // moving again: from where it hangs
	}
	if (!bPosed && !bDead)
	{
		PoseNow(false);
	}
	if (bRigDirty || bRigForce || bRigStale)
	{
		RigFlush(Tolerance, bRigForce || bRigStale);
	}
}

void AVLKing::RigLateUpdate(UWorld* World, ELevelTick TickType, float DeltaSeconds)
{
	if (!World || !World->IsGameWorld() || GRigUnits.Num() == 0)
	{
		return;
	}
	GStatOn = CVarRigStats.GetValueOnGameThread() != 0;
	FRigTimer Timer(GStatLateCycles);
	FVLRigView View;
	View.bBatch = CVarRigBatch.GetValueOnGameThread() != 0;
	View.bLod = CVarRigLOD.GetValueOnGameThread() != 0;
	View.PixelError = FMath::Max(CVarRigPixelError.GetValueOnGameThread(), 0.f);
	View.FarDist = FMath::Max(CVarRigFarDist.GetValueOnGameThread(), 100.f);
	View.Margin = FMath::Max(CVarRigCullMargin.GetValueOnGameThread(), 100.f);
	View.bDepthGate = CVarUnitDepth.GetValueOnGameThread() != 0;
	View.bUnitGI = CVarUnitGI.GetValueOnGameThread() != 0;
	View.DepthFar = FMath::Max(CVarUnitDepthFar.GetValueOnGameThread(), 1000.f);
	View.RealDt = float(FApp::GetDeltaTime());
	View.Dt = DeltaSeconds;
	if (const APlayerController* PC = World->GetFirstPlayerController())
	{
		const AVLHUD* HUD = Cast<AVLHUD>(PC->GetHUD());
		View.bTitle = HUD && HUD->IsTitle();
		const ULocalPlayer* Player = PC->GetLocalPlayer();
		FSceneViewProjectionData Projection;
		if (Player && Player->ViewportClient && Player->ViewportClient->Viewport && Player->GetProjectionData(Player->ViewportClient->Viewport, Projection))
		{
			const int32 Width = Projection.GetConstrainedViewRect().Width();
			const double Scale = Projection.ProjectionMatrix.M[0][0];          // 1 / tan(half the view's angle)
			if (Width > 0 && Scale > 1e-6 && Projection.ProjectionMatrix.M[3][3] < 1.0)
			{
				GetViewFrustumBounds(View.Frustum, Projection.ComputeViewProjectionMatrix(), false);
				View.Eye = Projection.ViewOrigin;
				View.CmPerPx = 2.0 / (Scale * double(Width));
				View.bValid = true;
			}
		}
	}
	for (int32 i = GRigUnits.Num() - 1; i >= 0; --i)
	{
		AVLKing* Unit = GRigUnits[i];
		if (Unit && Unit->GetWorld() == World)
		{
			Unit->RigLate(View);
		}
	}
	if (CVarRigStats.GetValueOnGameThread() != 0)
	{
		++GStatFrames;
		const double Now = FPlatformTime::Seconds();
		if (Now - GStatLast >= 2.0)
		{
			const float F = 1.f / FMath::Max(GStatFrames, 1);
			const double Ms = 1000.0 * FPlatformTime::GetSecondsPerCycle64() * F;
			// (pose: building the poses, in the units' ticks and in the late pass; on the old path that is where the
			// components move. late: the whole late pass, its poses and writes included)
			UE_LOG(LogSovereignRealms, Log, TEXT("rig: %.0f units, per frame %.1f posed, %.1f written, %.0f parts to the renderer | pose %.2f ms, write %.2f ms, late pass %.2f ms (batch %d, lod %d)"),
				GStatUnits * F, GStatPosed * F, GStatFlushed * F, GStatSent * F, GStatPoseCycles * Ms, GStatFlushCycles * Ms, GStatLateCycles * Ms, View.bBatch ? 1 : 0, View.bLod ? 1 : 0);
			GStatLast = Now;
			GStatFrames = GStatUnits = GStatPosed = GStatFlushed = GStatSent = 0;
			GStatPoseCycles = GStatFlushCycles = GStatLateCycles = 0;
		}
	}
	else
	{
		GStatFrames = GStatUnits = GStatPosed = GStatFlushed = GStatSent = 0;
		GStatPoseCycles = GStatFlushCycles = GStatLateCycles = 0;
	}
}

void AVLKing::UpdateCustomDepth(bool bWant)
{
	bDepthOn = bWant;
	for (UStaticMeshComponent* PartMesh : Meshes)
	{
		if (PartMesh)
		{
			PartMesh->SetRenderCustomDepth(bWant);
		}
	}
}

// ------------------------------------------------------------------------------------------------ the actor's side

void AVLKing::RigRegister(bool bRegister)
{
	if (bRegister)
	{
		GRigUnits.AddUnique(this);
		if (!GRigLateHandle.IsValid())
		{
			GRigLateHandle = FWorldDelegates::OnWorldPostActorTick.AddStatic(&AVLKing::RigLateUpdate);
		}
	}
	else
	{
		GRigUnits.RemoveSwap(this);
	}
}

void AVLKing::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	RigRegister(false);
	Super::EndPlay(EndPlayReason);
}

void AVLKing::WakeRigPosers()
{
	for (const FRigPoser& P : RigPosers)
	{
		if (UActorComponent* PoserOwner = P.Owner.Get())
		{
			PoserOwner->SetComponentTickEnabled(true);
		}
	}
}

void AVLKing::PossessedBy(AController* NewController)
{
	Super::PossessedBy(NewController);
	if (Cast<APlayerController>(NewController))
	{
		EnsureCameraRig();      // the player's now: the hero camera and the overview's
	}
	else if (NewController)
	{
		// Its AI controller only stands for "not the player's" (AVLKing::PollInput walks it to its orders): the tick
		// that turns the controller to its focus has nothing to do (no focus is ever set, and the unit does not take
		// its controller's rotation). 348 of them ticked every frame.
		NewController->SetActorTickEnabled(false);
	}
	WakeRigPosers();            // (its bow or its spyglass may be in other hands now)
}

void AVLKing::UnPossessed()
{
	Super::UnPossessed();
	WakeRigPosers();
}

void AVLKing::EnsureCameraRig()
{
	// Only a pawn the player controls needs these (every troop had them, ticking): made when the controls first pass
	// to it, and kept from then on (a view blending away from it still looks through them).
	if (!Boom)
	{
		Boom = NewObject<UVLHeroBoom>(this, TEXT("HeroBoom"));        // (a spring arm kept out of the ground: VLCameraGround.h)
		Boom->SetupAttachment(GetCapsuleComponent());
		Boom->TargetArmLength = TargetArm;
		Boom->SocketOffset = FVector(0.f, 0.f, 40.f);
		Boom->bUsePawnControlRotation = true;
		Boom->bEnableCameraLag = true;
		Boom->CameraLagSpeed = 7.f * BoomLagScale;
		Boom->bDoCollisionTest = false;             // a high diorama camera: trees and roofs must not yank it in
		Boom->SetRelativeLocation(FVector(0.f, 0.f, GetCapsuleComponent()->GetUnscaledCapsuleHalfHeight() * 0.45f));
		Boom->RegisterComponent();
	}
	if (!Camera)
	{
		Camera = NewObject<UCameraComponent>(this, TEXT("HeroCamera"));
		Camera->SetupAttachment(Boom);
		Camera->SetFieldOfView(CameraFOV);
		Camera->bUsePawnControlRotation = false;
		Camera->RegisterComponent();
	}
	if (!OverviewCamera && GetWorld())
	{
		OverviewCamera = GetWorld()->SpawnActor<ACameraActor>(FVector::ZeroVector, FRotator::ZeroRotator);
		if (OverviewCamera)
		{
			OverviewCamera->GetCameraComponent()->SetFieldOfView(OverviewFOV);
			OverviewCamera->GetCameraComponent()->SetConstraintAspectRatio(false);
			UpdateOverviewCamera(0.f, true);
		}
	}
}

namespace
{
	FAutoConsoleCommandWithWorldAndArgs CmdRigCheck(TEXT("vl.RigCheck"),
		TEXT("log how far the units' components are from their pose buffer (cm, degrees): 0 for a unit in view once the frame's late pass has run"),
		FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>&, UWorld* World)
		{
			int32 Units = 0, Off = 0;
			double WorstCm = 0.0, WorstDeg = 0.0, PathCm = 0.0, PathDeg = 0.0;
			FString WorstUnit;
			for (AVLKing* Unit : GRigUnits)
			{
				if (Unit && Unit->GetWorld() == World && Unit->IsAlive())
				{
					double Cm = 0.0, Deg = 0.0;
					Unit->RigCompare(Cm, Deg);
					++Units;
					Off += (Cm > 0.01 || Deg > 0.01) ? 1 : 0;
					WorstCm = FMath::Max(WorstCm, Cm);
					WorstDeg = FMath::Max(WorstDeg, Deg);
					Unit->RigSelfCheck(Cm, Deg);
					if (Cm > PathCm || Deg > PathDeg)
					{
						WorstUnit = Unit->GetDisplayName();
					}
					PathCm = FMath::Max(PathCm, Cm);
					PathDeg = FMath::Max(PathDeg, Deg);
				}
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("rig check: %d units. Old path against new, the same pose: worst %.5f cm %.5f deg (%s). Components against the buffer: %d away (out of view or between far poses), worst %.3f cm %.3f deg"),
				Units, PathCm, PathDeg, *WorstUnit, Off, WorstCm, WorstDeg);
		}));
}
