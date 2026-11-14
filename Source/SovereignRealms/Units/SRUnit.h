// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Common/SRTypes.h"
#include "SRUnit.generated.h"

class USRBattleSubsystem;
class USRRingComponent;
class UStaticMesh;
class UStaticMeshComponent;
class UMaterialInstanceDynamic;

/**
 * One troop. Greybox body built from engine basic shapes, moved by lightweight
 * steering (seek + arrive + separation) and animated procedurally with transforms.
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
	void OrderStop();

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
	FVector GetAimPoint() const { return SimPos + FVector(0.f, 0.f, GetBodyHeight() * 0.55f); }
	float GetHealth() const { return Health; }
	float GetHealthFrac() const;
	double GetLastDamagedTime() const { return LastDamagedTime; }
	ESROrder GetOrder() const { return Order; }
	ASRUnit* GetTarget() const { return Target.Get(); }
	ESRAttackPhase GetAttackPhase() const { return AttackPhase; }

	void SetHome(const FVector2D& InHome) { Home = InHome; }

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
	void CancelAttack();
	void ResetProgress();
	void Die(ASRUnit* Killer, const FVector2D& HitDir);
	FVector2D ComputeAvoidance(const FVector2D& Desired) const;
	bool CanStep(const FVector2D& Step) const;
	void TryMove(const FVector2D& Step, float Dt);
	void FollowGround(float Dt);

	// --- visuals (SRUnitVisuals.cpp) ---
	void BuildVisuals();
	UStaticMeshComponent* AddPart(UStaticMesh* Mesh, USceneComponent* Parent, const FVector& Loc, const FRotator& Rot, const FVector& Scale, const FLinearColor& Color);
	void StepDeathVisual(float Dt);
	void UpdateFlash(float Dt);
	void UpdateRing(float Dt);
	FVector GetMuzzleLocation() const;

	UPROPERTY(VisibleAnywhere, Category = "Unit") TObjectPtr<USceneComponent> Root;
	/** Everything that bobs, leans, squashes and topples hangs off this. */
	UPROPERTY(VisibleAnywhere, Category = "Unit") TObjectPtr<USceneComponent> VisualRoot;
	UPROPERTY(Transient) TObjectPtr<USceneComponent> WeaponPivot;
	UPROPERTY(Transient) TObjectPtr<UStaticMeshComponent> NockedArrow;
	UPROPERTY(Transient) TObjectPtr<USRRingComponent> Ring;
	UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInstanceDynamic>> PartMIDs;
	TArray<FLinearColor> PartColors;

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
	FVector2D Home = FVector2D::ZeroVector;
	TWeakObjectPtr<ASRUnit> Target;
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
	float LastAppliedFlash = -1.f;
	float Squash = 0.f;
	float AckClock = 1000.f;
	float AnimTime = 0.f;
	float WalkPhase = 0.f;
	float SmoothedSpeedFrac = 0.f;
	float SmoothedTurnLean = 0.f;
};
