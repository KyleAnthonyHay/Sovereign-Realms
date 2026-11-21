// ================================================================================================================
// DEPRECATED: superseded by VoxelLab (VoxelLab/Source/VoxelLab). This module is the first draft of Sovereign Realms and
// is no longer developed. Its game logic was reimplemented there (VLBattle, VLEnemyAI, VLCommand, VLHUD, the combat
// components); the Builder, Scout, Medic, Catapult, Horseman, construction, fog of war and saves remain only here.
// See README.md at the repository root. Kept so the old project still builds; do not delete.
// ================================================================================================================
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
	/** Builders: go to a building site (or a damaged building of their own) and work on it until it is done. */
	void OrderBuild(ASRBuilding* InBuilding);
	/** At the walls of this building, working on it (a builder with the Build order). */
	bool IsWorkingOn(const ASRBuilding* Building) const { return bWorking && Order == ESROrder::Build && BuildTarget.Get() == Building && IsActive(); }
	bool IsBuilder() const { return Stats().bBuilder; }
	/** How hard it is to notice (FSRUnitStats::NoticeScale): 1 = like anyone, under 1 = only from closer. */
	float GetNoticeScale() const { return Stats().NoticeScale; }
	/** Would a foe that notices ordinary troops out to Range notice this one at DistSq (squared, centre to centre)? */
	bool IsNoticedAt(float DistSq, float Range) const { return DistSq <= FMath::Square(Range * Stats().NoticeScale); }
	ASRBuilding* GetBuildTarget() const { return Order == ESROrder::Build ? BuildTarget.Get() : nullptr; }
	/** Guard a Builder of our own (Ward) or a building of our own (WardBuilding): keep to Offset from it, fight what
	 * comes near it (within GuardLeash), never chase far. Builders do not guard, and only Builders can be guarded. */
	void OrderGuard(ASRUnit* Ward, ASRBuilding* WardBuilding, const FVector2D& Offset);
	static bool CanBeGuarded(const ASRUnit* U) { return U && U->IsBuilder(); }
	/** Wander the map on its own (unexplored and unseen ground first), picking a new spot on arrival; struck by a foe, it
	 * drops the roam and runs home to its castle. Meant for the Scout. */
	void OrderRoam();
	bool IsRoaming() const { return Order == ESROrder::Roam; }
	/** Medics: keep beside this troop of our own, following it, healing everyone round it. */
	void OrderHeal(ASRUnit* Ward);
	bool IsMedic() const { return UnitType == ESRUnitType::Medic; }
	ASRUnit* GetHealWard() const { return Order == ESROrder::Heal ? HealWard.Get() : nullptr; }
	/** A Passive Medic running from foes right now. */
	bool IsFleeing() const { return bFleeing; }
	/** Health back (capped at its maximum); returns how much it actually got. */
	float Heal(float Amount);
	ASRUnit* GetGuardedUnit() const { return Order == ESROrder::Guard ? GuardUnit.Get() : nullptr; }
	ASRBuilding* GetGuardedBuilding() const { return Order == ESROrder::Guard ? GuardBuilding.Get() : nullptr; }
	/** Move (or attack-move) through waypoints to the last point: how recruits and group moves get round buildings. */
	void OrderMovePath(const TArray<FVector2D>& Points, bool bAttackMove);
	int32 GetWaypointsLeft() const { return Waypoints.Num(); }
	/** Marching in a group: travel no faster than this (cm/s; 0 = own top speed). Set by a group move, cleared by
	 * any new order. */
	void SetPace(float Speed) { PaceSpeed = Speed; }
	/** Marching in formation: head for T (its place in the shape, which moves with the formation) at most at Pace.
	 * Keeps the move / attack-move order going without starting it afresh each frame. */
	void MarchTo(const FVector2D& T, float Pace, bool bAttackMove);

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
	/** One line of what it is doing (sr.Watch): order, target and distance, attack phase, speed. */
	FString DescribeState() const;
	/** A catapult: the nearest fighting foe inside its minimum range (it backs away from it), or none. */
	const ASRUnit* TooCloseThreat(const FVector2D& Pos) const;
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
	float GetBodyHeight() const
	{
		switch (UnitType)
		{
		case ESRUnitType::Archer: return 134.f;
		case ESRUnitType::Horseman: return 200.f;
		case ESRUnitType::Catapult: return 190.f;
		default: return 142.f;
		}
	}
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
	bool IsEngaged() const { return Target.IsValid() || TargetBuilding.IsValid() || (AttackPhase != ESRAttackPhase::Ready && UnitType != ESRUnitType::Medic); }

	// ---- Selection feedback ----
	void SetSelected(bool bInSelected);
	bool IsSelected() const { return bSelected; }
	void SetHovered(bool bInHovered) { bHovered = bInHovered; }
	/** Ring flashes in the attack colour: "this is the one you told them to hit". */
	void FlashTargeted() { TargetFlash = 0.7f; }

private:
	// --- simulation (SRUnit.cpp) ---
	void UpdateTargeting(float Dt);
	/** Builders: the Build order's walk and work; an idle builder looks for a job now and then. */
	void StepBuild(float Dt, FVector2D& Desired, FVector2D& FaceDir);
	void LookForWork(float Dt);
	void TickAttack(float Dt, ASRUnit* T);
	/** Starts the wind-up of a strike (and its swing sound). */
	void BeginSwing();
	/** Horses: the gallop under a rider at speed, the odd snort at rest. */
	void StepHorseSounds(float Dt);
	void Strike(ASRUnit* T);
	void StrikeBuilding(ASRBuilding* B);
	/** Steering toward a chase target: straight when the way is clear, otherwise along a grid path refreshed now and
	 * then. Toward (a building it is going to strike or work on): the path runs to whichever of its walls is nearest
	 * on foot, and Goal is only used once the way to it is clear. */
	FVector2D ChaseDir(const FVector2D& Goal, float Dt, const ASRBuilding* Toward = nullptr);
	/** Stuck on the way somewhere: plan the rest of the march again from where it stands (false: no fresh route, or
	 * it has asked too often on this order). */
	bool Repath();
	void CancelAttack();
	void ResetProgress();
	void Die(ASRUnit* Killer, const FVector2D& HitDir, bool bQuiet = false);
	/** Medics: flee (Passive), heal what is in reach, follow the ward, go to the wounded (Assertive). True when it
	 * has decided the medic's movement this step (the ordinary order handling is skipped). */
	bool StepMedic(float Dt, FVector2D& Desired, FVector2D& FaceDir);
	/** The bandaging lands: the patient gets MedicHealAmount back (if it is still within touch). */
	void HealPulse();
	/** The wounded troop of our side (not this one) within Radius of Centre that most needs it (worst hurt, then
	 * nearest this Medic), or null. bAvoidFoes: none with a foe close to it (a Passive Medic does not go there). */
	ASRUnit* FindWounded(const FVector2D& Centre, float Radius, bool bAvoidFoes) const;
	/** Close enough to touch it? */
	bool InContact(const ASRUnit* Other) const;
	TWeakObjectPtr<ASRUnit> HealWard;
	TWeakObjectPtr<ASRUnit> Patient;
	bool bFleeing = false;
	/** Roaming: head for a fresh spot (false: none found). */
	bool PickRoamPoint();
	/** Struck while roaming: run for the castle's gate. */
	void FleeHome();
	float RoamLegTime = 0.f;
	/** Where the guarded thing is now (false: it is gone). */
	bool GuardWardPos(FVector2D& Out) const;
	TWeakObjectPtr<ASRUnit> GuardUnit;
	TWeakObjectPtr<ASRBuilding> GuardBuilding;
	FVector2D GuardOffset = FVector2D::ZeroVector;
	FVector2D GuardLastWard = FVector2D::ZeroVector;
public:
	/** Sent away by its own side (a stuck troop): it falls out quietly, no cry, no shake. */
	void Dismiss();
private:
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
	/** Thin ring in the platoon's colour, under every member of a platoon. */
	UPROPERTY(Transient) TObjectPtr<USRRingComponent> PlatoonRing;
	int32 PlatoonRingShown = -2;   // the platoon its colour was set for (-1 = hidden)

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
	TWeakObjectPtr<const ASRBuilding> ChaseBuilding;
	float ChaseRepath = 0.f;
	int32 RepathsLeft = 0;        // fresh routes it may still ask for on this order
	float RetargetTimer = 0.f;
	float BestDist = 0.f;
	float NoProgressTime = 0.f;
	bool bReturnHomeWhenDone = false;
	double LastProvokedTime = -100.0;
	float PaceSpeed = 0.f;
	TWeakObjectPtr<ASRBuilding> BuildTarget;
	bool bWorking = false;
	float WorkClock = 0.f;
	float JobSearchTimer = 0.f;
	int32 LastWorkFrame = -1;

	// combat
	float Health = 1.f;
	ESRAttackPhase AttackPhase = ESRAttackPhase::Ready;
	float PhaseTime = 0.f;
	float Cooldown = 0.f;
	double LastStrikeTime = -100.0;
	float DustClock = 0.f;   // cavalry charge: the first blow after a rest
	TWeakObjectPtr<class UAudioComponent> GallopSound;
	float SnortClock = 0.f;
	float GallopRetry = 0.f;
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
	// FollowGround: where the ground was last sampled, and whether the unit has come to rest on it (no trace while it stands there)
	FVector2D GroundSampleXY = FVector2D::ZeroVector;
	bool bGroundSettled = false;
	bool bSpriteShown = true;
	bool bCulled = false;      // off screen: presentation skipped (SpriteView.CullRadius)
	bool bShadowCasting = true;
	FVector4 AppliedSpriteData = FVector4(-1.f, -1.f, -1.f, -1.f);
	FVector4 AppliedShadowData = FVector4(-1.f, -1.f, -1.f, -1.f);
	float AppliedBlob = -1.f;
};
