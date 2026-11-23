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
class UVLArrowTrailComponent;
class UMaterialInstanceDynamic;

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
 *
 * THE STREAK. Every arrow in flight draws a thin pale line along the stretch it has just flown (vl.Arrow.Trail 0|1),
 * the last vl.Arrow.TrailLength seconds of it, vl.Arrow.TrailWidth cm wide at the arrow and tapering to nothing at
 * its far end; once the arrow has landed (or struck someone) the streak runs out behind it and is gone. Nothing is
 * kept per frame: the flight is a parabola, so where the arrow was s seconds ago follows from where it is and how it
 * flies now. All the streaks are one mesh (UVLArrowTrailComponent on the arrows' actor), in the world and depth
 * tested, with a dynamic instance of M_PlacementGhost (translucent, unlit) tinted pale gold. Looks only: nothing of
 * the flight, the hits or the damage depends on it.
 */
UCLASS()
class SOVEREIGNREALMS_API UVLArrows : public UTickableWorldSubsystem
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
	/** An arrow loosed by a building (a watch tower, the castle's walls) of a team: it passes through its own side. */
	void FireFrom(AActor* Source, int32 Team, const FVector& Tip, const FVector& Velocity, float Gravity, float Damage);

	/** A blow with the bow itself on a training dummy: it rocks a little (Degrees at most; a sword or an arrow rocks
	 *  it 24), a dull knock, and Damage for when dummies have health. */
	void BashDummy(AActor* Dummy, const FVector& Away, float Degrees, float Damage, AVLKing* By);
	/** The swish of the bow swung as a club. */
	void PlaySwish(const FVector& At);
	/** The bow's creak as an archer starts to draw it (S_BowDraw; vl.Arrow.DrawVolume, at most one every vl.Arrow.DrawGap). */
	void PlayDraw(const FVector& At);
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
		TWeakObjectPtr<AActor> Source;     // who loosed it (the shooter, or a building)
		int32 Team = -1;                   // it hits foes of this team (-1: anyone, as before)
	};
	/** The first foe of the arrow's team whose body (its capsule) the stretch From..To passes through, and how far along. */
	class AVLKing* UnitOnPath(const FArrow& A, const FVector& From, const FVector& To, float& OutT) const;
	TArray<FArrow> Arrows;

	/** The streak of an arrow that is no longer flying (it landed, struck someone or was lost), until it has run out:
	 *  where the flight ended, how it flew there, how long it had flown, and how long ago that was. */
	struct FTail
	{
		FVector End = FVector::ZeroVector;
		FVector Velocity = FVector::ZeroVector;
		float Gravity = 980.f;
		float Flight = 0.f;
		float Since = 0.f;
	};
	TArray<FTail> Tails;
	/** The arrow's flight ends at At: its streak runs out from there. */
	void EndTrail(const FArrow& A, const FVector& At);
	/** This frame's streaks to their component. */
	void UpdateTrails(float DeltaSeconds);

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
	TObjectPtr<UVLArrowTrailComponent> Trail;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> TrailMaterial;

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
	TArray<TObjectPtr<USoundBase>> DrawSounds;

	UPROPERTY(Transient)
	TObjectPtr<USoundAttenuation> Pan;

	bool bLoaded = false;
	int32 Fired = 0;
	int32 DummyHits = 0;
	int32 LastClip[5] = { -1, -1, -1, -1, -1 };
	double LastTime[5] = { -1.0, -1.0, -1.0, -1.0, -1.0 };

	void Load();
	int32 Take();
	void Release(int32 Index);
	void Land(int32 Index, const FHitResult& Hit);
	void Place(int32 Index);
	void SetFade(int32 Index, float Alpha);
	void Play(int32 Kind, const FVector& At, float Volume);
};
