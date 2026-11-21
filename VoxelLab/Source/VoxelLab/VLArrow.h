#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "VLArrow.generated.h"

class AVLKing;
class UStaticMesh;
class UStaticMeshComponent;
class UMaterialInterface;
class USoundBase;
class USoundAttenuation;

/** The loose arrow as the archer's generator models it (Tools/blender/assets/troop_archer.py, "arrow" in
 *  SourceArt/Meshes/SM_Archer.json), in character space: the mesh's origin is where her right fist holds the shaft. */
namespace VLArrowGeom
{
	/** From the fist to the point, as modelled (json "dir", Blender (x, y, z) -> (-y, -x, z)). */
	inline const FVector Dir(0.90631, -0.04418, 0.4203);
	/** cm from the mesh's origin to the point, and back to the nock. */
	inline constexpr float TipOffset = 50.f;
	inline constexpr float NockOffset = 25.f;
	inline constexpr float Length = TipOffset + NockOffset;
	/** The mesh (also the one in her hand). */
	inline const TCHAR* MeshPath = TEXT("/Game/Voxel/Troops/Archer/SM_Archer_Arrow.SM_Archer_Arrow");
	/** Where the mesh's origin goes, and how the mesh is turned, for an arrow whose point is at Tip, flying along Dir. */
	FTransform MeshTransform(const FVector& Tip, const FVector& Along, float MeshYaw = -90.f);
}

/**
 * Every arrow in the air or stuck somewhere: one pool of static mesh components on one actor, moved here (no actor,
 * no tick and no allocation per arrow).
 *
 * An arrow flies a ballistic arc (its own speed, gravity pulling it down), turned along its path. A trace along each
 * frame's stretch finds what it hits: a training dummy (an actor tagged Dummy: the arrow sticks in it, rides it and
 * the dummy rocks, UVLSwordFx::HitDummy), water (it is gone), anything else (it sticks there). vl.Arrow.Life seconds
 * after landing it is taken back into the pool, fading out over the last vl.Arrow.Fade of them (the dither of
 * M_VoxArrow, per arrow through custom primitive data; without that material it shrinks instead). An arrow that
 * hits nothing is taken back after vl.Arrow.MaxFlight seconds. The pool grows to vl.Arrow.Pool arrows; beyond that
 * the oldest one is reused.
 *
 * Sounds (S_BowRelease*, S_ArrowFly, S_ArrowHitWood*, S_ArrowHitGround*; the dummy's thunk is UVLSwordFx's), fading
 * with the distance from where the player is looking as the troops' shuffle does: vl.Arrow.ReleaseVolume, FlyVolume,
 * HitVolume, Near, Range, SoundGap. vl.ArcherLog 1 logs every shot and every landing; vl.Arrows logs the pool.
 */
UCLASS()
class VOXELLAB_API UVLArrows : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	static UVLArrows* Get(const UObject* WorldContext);
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;
	virtual void Tick(float DeltaSeconds) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UVLArrows, STATGROUP_Tickables); }

	/** Looses an arrow: its point at Tip, flying at Velocity (cm/s), pulled down by Gravity (cm/s2). Ignore: an actor
	 *  it passes through for its first moments (the tower the archer stands on). The bow's twang and the whoosh. */
	void Fire(AVLKing* Shooter, const FVector& Tip, const FVector& Velocity, float Gravity, AActor* Ignore = nullptr, float Damage = 10.f);

	/** A blow with the bow itself on a training dummy: it rocks a little (Degrees at most; a sword or an arrow rocks
	 *  it 24), a dull knock, and Damage for when dummies have health. */
	void BashDummy(AActor* Dummy, const FVector& Away, float Degrees, float Damage, AVLKing* By);
	/** The swish of the bow swung as a club. */
	void PlaySwish(const FVector& At);
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;

	/** The direction to loose an arrow in at Speed so that it comes down on To (the low arc). False: To is out of
	 *  range (OutDir is then the longest shot that way, at 45 degrees). */
	static bool SolveArc(const FVector& From, const FVector& To, float Speed, float Gravity, FVector& OutDir);

	/** The pull (cm/s2) that makes an arrow loosed at Speed over FlatDistance cm of level ground rise
	 *  PeakHeight * (FlatDistance / PeakDistance) ^ Growth cm above the straight line at the top of its arc: a chosen,
	 *  gently growing arc in place of the one a fixed pull gives (which grows with the square of the distance).
	 *  Never more than MaxGravity, so a shot is never more arched than the plain ballistic one (short shots keep it).
	 *  PeakHeight <= 0: MaxGravity. Give the result to SolveArc and to Fire. */
	static float ArcGravity(float FlatDistance, float Speed, float MaxGravity, float PeakHeight, float PeakDistance, float Growth);

	int32 NumFlying() const;
	int32 NumStuck() const;
	int32 PoolSize() const { return Arrows.Num(); }
	int32 NumFired() const { return Fired; }
	int32 NumDummyHits() const { return DummyHits; }

private:
	enum class EState : uint8 { Free, Flying, Stuck };
	struct FArrow
	{
		EState State = EState::Free;
		FVector Tip = FVector::ZeroVector;
		FVector Velocity = FVector::ZeroVector;
		float Gravity = 980.f;
		float Damage = 10.f;
		float Age = 0.f;            // seconds in the air, then seconds since it landed
		float Shown = -1.f;         // the fade last given to its component
		TWeakObjectPtr<AActor> Ignore;
		TWeakObjectPtr<AVLKing> Shooter;
	};
	TArray<FArrow> Arrows;

	struct FKnock
	{
		TWeakObjectPtr<AActor> Actor;
		FQuat Rest = FQuat::Identity;
		FVector Away = FVector::ForwardVector;
		float Degrees = 7.f;
		float Time = 0.f;
	};
	TArray<FKnock> Knocks;
	/** How every dummy stood when play began (so a knock always settles back to that). */
	TMap<TWeakObjectPtr<AActor>, FQuat> DummyRest;

	UPROPERTY(Transient)
	TObjectPtr<AActor> Holder;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> Components;

	UPROPERTY(Transient)
	TObjectPtr<UStaticMesh> Mesh;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> FadeMaterial;

	UPROPERTY(Transient)
	TArray<TObjectPtr<USoundBase>> ReleaseSounds;

	UPROPERTY(Transient)
	TArray<TObjectPtr<USoundBase>> FlySounds;

	UPROPERTY(Transient)
	TArray<TObjectPtr<USoundBase>> WoodSounds;

	UPROPERTY(Transient)
	TArray<TObjectPtr<USoundBase>> GroundSounds;

	UPROPERTY(Transient)
	TObjectPtr<USoundAttenuation> Pan;

	bool bLoaded = false;
	int32 Fired = 0;
	int32 DummyHits = 0;
	int32 LastClip[4] = { -1, -1, -1, -1 };
	double LastTime[4] = { -1.0, -1.0, -1.0, -1.0 };

	void Load();
	int32 Take();
	void Release(int32 Index);
	void Land(int32 Index, const FHitResult& Hit);
	void Place(int32 Index);
	void SetFade(int32 Index, float Alpha);
	void Play(int32 Kind, const FVector& At, float Volume);
};
