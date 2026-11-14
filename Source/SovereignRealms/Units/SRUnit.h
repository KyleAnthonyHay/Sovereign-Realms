// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Common/SRTypes.h"
#include "Units/SRSprite.h"
#include "SRUnit.generated.h"

class USRBattleSubsystem;
class ASRBuilding;
class USRRingComponent;
class UStaticMeshComponent;
class UDecalComponent;

/**
 * One troop: a pixel-art sprite on a camera-facing card, moved by lightweight
 * steering (seek + arrive + separation). The sprite frame is chosen from the
 * simulation state every frame (see SRUnitVisuals.cpp and SPRITE_SPEC.md).
 *
 * The actor origin is at the unit's feet on the ground. Units have no collision
 * components: spacing, picking and ground-following are all done with maths and
 * line traces against WorldStatic, so they keep working on uneven terrain.
 *
 * Simulation lives in SRUnit.cpp, visuals / animation in SRUnitVisuals.cpp.
 * USRBattleSubsystem steps every unit each frame (units do not tick themselves).
 */
UCLASS()
class SOVEREIGNREALMS_API ASRUnit : public AActor
{
	GENERATED_BODY()

public:
	ASRUnit();

	/** Must be called right after spawning. SpawnDelay staggers the pop-in. */
	void InitUnit(ESRUnitType InType, ESRTeam InTeam, float InSpawnDelay, const FString& InLabel);

	// ---- Orders (take effect the same frame) ----
	void OrderMove(const FVector2D& Dest);
	void OrderAttackMove(const FVector2D& Dest);
	void OrderAttack(ASRUnit* InTarget);
	void OrderAttackBuilding(ASRBuilding* InTarget);
	void OrderStop();
	/** Stand fast: strike / shoot only what is in reach, never step out to chase. */
	void OrderHold();
	/** Move (or attack-move) through waypoints to the last point: how recruits and group moves get round buildings. */
	void OrderMovePath(const TArray<FVector2D>& Points, bool bAttackMove);
	int32 GetWaypointsLeft() const { return Waypoints.Num(); }

	/** Little hop that says "order received". */
	void Acknowledge(float Delay);

	// ---- Driven by USRBattleSubsystem ----
	void StepSim(float Dt);
	void StepVisual(float Dt);
	/** Positional push from the overlap pass; respects walls. */
	void Nudge(const FVector2D& Delta);

	void ReceiveDamage(float Amount, ASRUnit* From, const FVector2D& HitDir, float Knockback, bool bHeavy);
	/** An ally was attacked nearby: join in if idle. */
	void AlertTo(ASRUnit* Threat);

	// ---- Queries ----
	const FSRUnitStats& Stats() const;
	ESRUnitType GetUnitType() const { return UnitType; }
	ESRTeam GetTeam() const { return Team; }
	const FString& GetLabel() const { return Label; }
	bool IsAlive() const { return !bDead; }
	/** Alive and finished spawning: selectable, commandable, targetable. */
	bool IsActive() const { return !bDead && bActive; }
	bool IsCorpseExpired() const;
	const FVector& GetSimPos() const { return SimPos; }
	FVector2D GetPos2D() const { return FVector2D(SimPos.X, SimPos.Y); }
	FVector2D GetVelocity2D() const { return Velocity; }
	FVector2D GetFacingDir() const;
	float GetRadius() const { return Stats().Radius; }
	float GetPushMass() const;
	/** Standing its ground (idle, or committed to a swing) rather than travelling. */
	bool IsPlanted() const;
	float GetBodyHeight() const { return UnitType == ESRUnitType::Archer ? 134.f : 142.f; }
	/** Mid-torso of the sprite as it appears on screen: where arrows land and what box selection tests. */
	FVector GetAimPoint() const;
	/** A point just above the sprite's head as it appears on screen (health bars). */
	FVector GetOverheadPoint() const;
	/** Feet-to-head segment of the sprite as it appears on screen, for cursor picking. */
	void GetPickSegment(FVector& OutFeet, FVector& OutHead) const;
	/** Sprite sheet cell currently shown (for the debug status log). */
	ESRSpriteAnim GetSpriteAnim() const { return SpriteAnim; }
	int32 GetSpriteFrame() const { return SpriteFrame; }
	int32 GetSpriteFacing() const { return FacingIndex; }
	float GetHealth() const { return Health; }
	/** Saved games: restore health directly (no hit reaction). */
	void SetHealthForLoad(float InHealth) { Health = FMath::Clamp(InHealth, 1.f, Stats().MaxHealth); }
	float GetHealthFrac() const;
	double GetLastDamagedTime() const { return LastDamagedTime; }
	ESROrder GetOrder() const { return Order; }
	ASRUnit* GetTarget() const { return Target.Get(); }
	ESRAttackPhase GetAttackPhase() const { return AttackPhase; }

	void SetHome(const FVector2D& InHome) { Home = InHome; }
	FVector2D GetHome() const { return Home; }
	ASRBuilding* GetTargetBuilding() const { return TargetBuilding.Get(); }

	// ---- platoons ----
	void SetStance(ESRStance InStance) { Stance = InStance; }
	ESRStance GetStance() const { return Stance; }
	/** Platoon slot (0 .. MaxPlatoons-1), or INDEX_NONE. */
	void SetPlatoon(int32 Index) { Platoon = Index; }
	int32 GetPlatoon() const { return Platoon; }
	/** Busy with a fight: has a target or is mid-swing. */
	bool IsEngaged() const { return Target.IsValid() || TargetBuilding.IsValid() || AttackPhase != ESRAttackPhase::Ready; }

	// ---- Selection feedback ----
	void SetSelected(bool bInSelected);
	bool IsSelected() const { return bSelected; }
	void SetHovered(bool bInHovered) { bHovered = bInHovered; }
	/** Ring flashes in the attack colour: "this is the one you told them to hit". */
	void FlashTargeted() { TargetFlash = 0.7f; }

private:
	// --- simulation (SRUnit.cpp) ---
	void UpdateTargeting(float Dt);
	void TickAttack(float Dt, ASRUnit* T);
	void Strike(ASRUnit* T);
	void StrikeBuilding(ASRBuilding* B);
	/** Steering toward a chase target: straight when the way is clear, otherwise along a grid path refreshed now and then. */
	FVector2D ChaseDir(const FVector2D& Goal, float Dt);
	void CancelAttack();
	void ResetProgress();
	void Die(ASRUnit* Killer, const FVector2D& HitDir);
	FVector2D ComputeAvoidance(const FVector2D& Desired) const;
	bool CanStep(const FVector2D& Step) const;
	void TryMove(const FVector2D& Step, float Dt);
	void FollowGround(float Dt);

	// --- visuals (SRUnitVisuals.cpp) ---
	void BuildVisuals();
	void StepDeathVisual(float Dt);
	void UpdateRing(float Dt);
	/** Writes the sheet cell, flash and fade to the cards (custom primitive data) and places them for this frame. */
	void ApplySprite(ESRSpriteAnim Anim, int32 Frame, float Fade, const FVector& Offset, const FVector2D& CardScale);
	void SetSpriteShown(bool bShown);
	FVector GetMuzzleLocation() const;

	UPROPERTY(VisibleAnywhere, Category = "Unit") TObjectPtr<USceneComponent> Root;
	/** Carries the sprite card; offset by the lunge and the acknowledge hop (local +X is the unit's facing). */
	UPROPERTY(VisibleAnywhere, Category = "Unit") TObjectPtr<USceneComponent> VisualRoot;
	/** The visible sprite: SM_UnitCard, parallel to the view plane, pivot at the feet. Never casts a shadow. */
	UPROPERTY(Transient) TObjectPtr<UStaticMeshComponent> SpriteCard;
	/** Hidden, shadow-only copy showing the frame as the sun sees it. */
	UPROPERTY(Transient) TObjectPtr<UStaticMeshComponent> ShadowCard;
	/** Stepped contact shadow under the feet. */
	UPROPERTY(Transient) TObjectPtr<UDecalComponent> Blob;
	UPROPERTY(Transient) TObjectPtr<USRRingComponent> Ring;

	UPROPERTY(Transient) TObjectPtr<USRBattleSubsystem> Battle;

	ESRUnitType UnitType = ESRUnitType::Shieldbearer;
	ESRTeam Team = ESRTeam::Player;
	FString Label;

	// kinematics
	FVector SimPos = FVector::ZeroVector;
	FVector2D Velocity = FVector2D::ZeroVector;
	FVector2D KnockVel = FVector2D::ZeroVector;
	float FacingYaw = 0.f;
	float YawRate = 0.f;
	int32 SlideSide = 0;          // which way we are sliding round an obstacle (-1 / 0 / +1)
	float UnblockedTime = 0.f;

	// orders
	ESROrder Order = ESROrder::Idle;
	FVector2D Destination = FVector2D::ZeroVector;
	TArray<FVector2D> Waypoints;   // points still to visit after Destination (Move / AttackMove)
	FVector2D Home = FVector2D::ZeroVector;
	TWeakObjectPtr<ASRUnit> Target;
	TWeakObjectPtr<ASRBuilding> TargetBuilding;
	ESRStance Stance = ESRStance::Aggressive;
	int32 Platoon = INDEX_NONE;
	TArray<FVector2D> ChasePath;
	FVector2D ChaseGoal = FVector2D::ZeroVector;
	float ChaseRepath = 0.f;
	float RetargetTimer = 0.f;
	float BestDist = 0.f;
	float NoProgressTime = 0.f;
	bool bReturnHomeWhenDone = false;
	double LastProvokedTime = -100.0;

	// combat
	float Health = 1.f;
	ESRAttackPhase AttackPhase = ESRAttackPhase::Ready;
	float PhaseTime = 0.f;
	float Cooldown = 0.f;
	float HitStopLeft = 0.f;
	double LastDamagedTime = -100.0;

	// life cycle
	bool bActive = false;
	bool bDead = false;
	float SpawnDelay = 0.f;
	float SpawnClock = 0.f;
	float DeathClock = 0.f;
	FVector2D DeathDir = FVector2D(1.f, 0.f);

	// presentation state
	bool bSelected = false;
	bool bHovered = false;
	bool bRingVisible = false;
	float RingPop = 0.f;
	float TargetFlash = 0.f;
	float HitFlash = 0.f;
	float Squash = 0.f;
	float AckClock = 1000.f;
	float AnimTime = 0.f;
	float HitAnimClock = 1000.f;

	// sprite state
	ESRSpriteAnim SpriteAnim = ESRSpriteAnim::Spawn;
	int32 SpriteFrame = 0;
	int32 FacingIndex = 0;        // row offset for the camera
	int32 ShadowFacingIndex = 0;  // row offset for the sun
	bool bWalking = false;
	bool bNextStepRight = false;
	float WalkDistance = 0.f;     // cm travelled in the current run; drives the walk cycle
	FVector2D LastVisualPos = FVector2D::ZeroVector;
	bool bSpriteShown = true;
	bool bCulled = false;      // off screen: presentation skipped (SpriteView.CullRadius)
	bool bShadowCasting = true;
	FVector4 AppliedSpriteData = FVector4(-1.f, -1.f, -1.f, -1.f);
	FVector4 AppliedShadowData = FVector4(-1.f, -1.f, -1.f, -1.f);
	float AppliedBlob = -1.f;
};
