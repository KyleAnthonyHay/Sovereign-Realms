#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "VLArcherCombat.generated.h"

class AVLKing;
class USceneComponent;
class UStaticMeshComponent;

/**
 * The archer's bow: how she carries it, how she shoots, and when. On every archer troop from the start (AVLTroop makes
 * it), ticking after the figure has been posed (AVLKing::Animate), whose arms, chest and head it then poses itself.
 *
 * CARRYING. The bow is modelled in her left fist, across the forearm, so it only stands upright while that forearm is
 * level: the left arm is held so (the upper arm a little forward, swinging less than the figure's gait would have it),
 * the forearm turned to whatever keeps the bow upright with its string towards her body, at a walk, at a run and in the
 * air. The string is two parts (BowStringU / BowStringL), swung and stretched from the limbs' tips to wherever the
 * string is held.
 *
 * SHOOTING, one shot: Reach (the right hand goes back to the quiver over her shoulder; an arrow appears in it, the
 * quiver keeps its own), Nock (the hand brings it to the string), Draw (the bow arm is out towards the target, the
 * chest turned side on, the string hand comes back to her cheek), Hold, Loose (the arrow leaves: UVLArrows flies it on
 * a ballistic arc from the bow, the string snaps straight). She faces what she shoots at; the arrow is aimed at that
 * point, off by up to the spread, on a shallow arc: its top ArcPeak cm above the straight line at ArcPeakDistance,
 * growing gently with the distance (ArcGrowth), never more arched than ArrowSpeed and ArrowGravity alone would have it.
 *
 * IN THE PLAYER'S HANDS (hero mode): pressing and holding the RIGHT mouse button draws and keeps her in the battle
 * state, for as long as it is held: she turns to face her aim, W A S D strafe relative to the camera at DrawMoveScale
 * of the walking speed, no running. Letting the button go looses (let go before the bow is fully drawn, she finishes
 * the draw and looses: a quick shot). A LEFT click while the right button is held LOCKS the draw: she stays drawn,
 * facing her aim, with the right button let go, and the next right press looses (that press draws nothing more: let
 * go and hold again for a fresh draw). A left click on a locked draw lets the string down without a shot, as do the
 * Esc menu and leaving her (the overview, another unit). A left click with no draw is a blow with the bow itself
 * (Bash): a short swipe across her front that knocks a training dummy within BashReach, less than an arrow does
 * (BashDamage against ArrowDamage, for when targets have health; the dummy rocks BashWobble degrees, not 24).
 * The right button does not turn the camera while she is played (the mouse, or Q / E, do). Gamepad: the right trigger
 * is the right button, the left shoulder the left.
 *
 * HER AIM is AVLKing::GetAimPoint: where the crosshair's ray meets the world ahead of her. What the ray meets between
 * the camera and her (a tree, a roof or a fence near the lens, drawn under the crosshair) does not count, nor do
 * friendly units or the tree crowns the camera cuts away; a foe's body does. The arrow is solved to pass exactly
 * through that point (from where its point is on the bow, with the pull it flies with), the spread being a point of
 * the same surface near it; if the ray meets nothing (the sky) it is loosed along the crosshair's ray. So she
 * shoots where the crosshair points and never turns round to shoot back at the camera. With the pointer shown (the
 * free view): what the pointer is over, else the ground at her feet.
 *
 * ON ORDERS (UVLCommand::OrderAttack / OrderAttackGround): she walks to within Range of the target by the usual routes
 * (an archer on the watch tower's lookout stays there and shoots from it, to TowerRange), turns to it and shoots every
 * ShotInterval seconds, each archer on her own beat, until given another order; at a spot of the ground GroundShots
 * times.
 *
 * Console: vl.Bow draw 0|1 | shoot | lock | cancel | bash | aim X Y [Z] | off (the played archer), vl.ShootAt <who> X Y [Z] [shots],
 * vl.Archers (every archer's state and how she holds the bow), vl.ArcherLog 1.
 */
UCLASS()
class SOVEREIGNREALMS_API UVLArcherCombat : public UActorComponent
{
	GENERATED_BODY()

public:
	UVLArcherCombat();

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

	/** Can this unit shoot (an archer troop)? */
	static bool CanFight(const AVLKing* Unit);
	/** The unit's component; made if it has none yet (and it is an archer). */
	static UVLArcherCombat* For(AVLKing* Unit, bool bCreate = true);
	/** The archers among Units go and shoot at Target until given another order. Returns how many were ordered. */
	static int32 OrderAttack(const TArray<AVLKing*>& Units, AActor* Target, bool bRun);
	/** The archers among Units shoot at that spot GroundShots times. */
	static int32 OrderAttackGround(const TArray<AVLKing*>& Units, const FVector& Ground, bool bRun);

	void Begin(AActor* InTarget, bool bRun);
	void BeginGround(const FVector& Ground, int32 Shots, bool bRun);
	/** No more shots on orders (an arrow on the string is still loosed). */
	void Stop();
	bool IsAttacking() const { return Mode != EMode::None; }
	/** What she was ordered to shoot at (null for a spot of the ground). */
	AActor* GetTarget() const { return Mode == EMode::Actor ? Target.Get() : nullptr; }

	// ---- the player's hands (also vl.Bow)
	/** As if the right mouse button were held / let go (letting go looses). */
	void SetTestDraw(bool bHeld) { bTestDraw = bHeld; SetComponentTickEnabled(true); }
	/** Loose as soon as the bow is drawn (a quick draw-and-shoot if it is not: a short click). */
	void Shoot();
	/** As the left mouse button: lock the draw the right button holds; let a locked draw down; else a blow with the bow. */
	void LeftButton();
	/** Let the string down without a shot (and end a lock). */
	void LetDown();
	/** A blow with the bow, if she is not drawing or shooting. */
	void StartBash();
	bool IsDrawLocked() const { return bLocked; }
	/** For the bar under the crosshair (AVLHUD::DrawHeroBits): is the played archer drawing, and how far along. OutDrawn:
	 *  0..1 of the way from the button going down to the bow fully drawn (the reach to the quiver, the nock and the
	 *  draw, by their own clocks: ReachSeconds + NockSeconds + DrawSeconds, QuickScale of them for a quick shot).
	 *  bOutReady: fully drawn and held (letting the button go now looses at once; before it, the shot waits for the
	 *  draw to finish). False: no draw on (at rest, or the arrow has just left). It only reads the shot's state. */
	bool GetDrawState(float& OutDrawn, bool& bOutReady) const;
	/** Aim at this point instead of the mouse pointer for a while. */
	void SetTestAim(const FVector& Point, float Seconds) { TestAim = Point; TestAimTime = Seconds; SetComponentTickEnabled(true); }
	/** Turn the hero camera, for a while, until the crosshair's ray passes through this point (vl.Bow look): the
	 *  crosshair is then on it, as if the mouse had put it there. */
	void SetTestLook(const FVector& Point, float Seconds) { TestLook = Point; TestLookTime = Seconds; SetComponentTickEnabled(true); }
	/** Drawing, holding or loosing: she faces her aim and strafes. */
	bool InBattleState() const { return bBattle; }
	/** One line for vl.Archers. */
	FString Describe() const;

	// ---- shooting
	/** cm/s an arrow leaves the bow at, and the most that pulls it down (cm/s2): the pull on short shots, and on any
	 *  shot with ArcPeak 0 (then the top of the arc grows with the square of the distance: 6 cm at 5 m, 23 at 10 m,
	 *  96 at 20 m, 228 at 30 m, 5 m at 42 m). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float ArrowSpeed = 6210.f;          // (2.7 times the first 2300)

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float ArrowGravity = 980.f;

	/** THE ARC. The top of an arrow's flight is ArcPeak cm above the straight line to its target for a shot over
	 *  ArcPeakDistance cm, and ArcPeak * (distance / ArcPeakDistance) ^ ArcGrowth for any other: the pull on each
	 *  arrow is chosen to give that (UVLArrows::ArcGravity), up to ArrowGravity, so close shots (within some 11 m
	 *  with these numbers) fly as plain ballistic ones. ArcGrowth 1: the arc grows in step with the distance
	 *  (2.5 cm a metre: 50 cm at 20 m, 75 at 30 m, 105 at 42 m); 2: with its square, as plain ballistics does;
	 *  0: the same height at any distance. A lower ArcPeak is a flatter shot at every distance. ArcPeak 0: off. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float ArcPeak = 50.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float ArcPeakDistance = 2000.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float ArcGrowth = 1.f;

	/** Seconds of each part of a shot; a quick shot (a left click without drawing) takes QuickScale of them. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float ReachSeconds = 0.26f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float NockSeconds = 0.26f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float DrawSeconds = 0.34f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float LooseSeconds = 0.24f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float QuickScale = 0.7f;

	/** Seconds the bow arm takes to come up to the aim, or back down. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float RaiseSeconds = 0.24f;

	/** Degrees an arrow may be off, left or right and up or down: in the player's hands, and on orders. In the
	 *  player's hands HeroSpread is not put on the launch but in the aim: a point of the same surface as the
	 *  crosshair's within distance x tan(HeroSpread) of it (or across the shot on a foe), hit exactly. On orders at a
	 *  spot of the ground SpreadPitch is scaled by the slope the arrow comes down at. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float HeroSpread = 0.3f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float SpreadYaw = 1.2f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float SpreadPitch = 0.8f;

	/** Degrees a second she turns to face her aim; she looses once within FaceWithin degrees of it. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float TurnRate = 620.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float FaceWithin = 6.f;

	/** What an arrow does to a foe it hits (x0.35 against buildings: UVLBattle), and a blow with the bow. The main game's
	 *  archer did 18 every 1.5 s (29 every 2.4 s, her ShotInterval, is the same damage a second); raised to 40 (+38%)
	 *  so archers are worth fielding (VLRules::Troop("Archer").Damage too). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float ArrowDamage = 40.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float BashDamage = 10.f;

	/** The blow with the bow: how long the swipe takes, how far in front of her it reaches (cm), and how many degrees
	 *  a dummy rocks from it. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float BashSeconds = 0.42f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float BashReach = 190.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float BashWobble = 7.f;

	/** In the player's hands, the crosshair on the sky (its ray meets nothing ahead): she aims at the point this far
	 *  along it, cm. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float SkyAimDistance = 3000.f;

	/** Drawing in the player's hands: this share of the walking speed (and no running). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer")
	float DrawMoveScale = 0.55f;

	// ---- on orders
	/** cm she shoots from: further off she walks to StandAt of it first. On the tower's lookout: TowerRange. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Orders")
	float Range = 3120.f;         // (2400 + 30%)

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Orders")
	float StandAt = 0.9f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Orders")
	float TowerRange = 5460.f;    // (4200 + 30%)

	/** Seconds from one shot to the next, each off by up to ShotJitter of it; the first after up to FirstShotDelay. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Orders")
	float ShotInterval = 2.4f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Orders")
	float ShotJitter = 0.15f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Orders")
	float FirstShotDelay = 0.9f;

	/** An attack-ground order: this many shots, landing within GroundScatter cm of the spot. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Orders")
	int32 GroundShots = 3;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Orders")
	float GroundScatter = 90.f;

	/** She aims this high up a dummy (cm above its foot). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Orders")
	float AimHeight = 95.f;

	// ---- the pose
	/** Carrying the bow: the upper arm this far forward and out (degrees), following this share of the gait's arm
	 *  swing; the bow leaning forward by CarryTilt, and RunTilt more at a full run; its string towards her body,
	 *  CarryStringIn degrees to her right of straight back. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Pose")
	float CarryArmPitch = 26.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Pose")
	float CarryArmOut = 8.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Pose")
	float CarrySwing = 0.3f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Pose")
	float CarryTilt = 4.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Pose")
	float RunTilt = 14.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Pose")
	float CarryStringIn = 26.f;

	/** The bow is turned in her fist (about its own length) so that the string passes this many degrees inside her
	 *  forearm, clear of the bracer. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Pose")
	float BowCant = 32.f;

	/** Aiming: the chest turned this far to her right (the bow shoulder to the target). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Pose")
	float ChestTwist = 48.f;

	/** Where the string hand comes back to: from the neck joint, cm forward, to her right and up (her cheek). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Pose")
	FVector Anchor = FVector(6.f, 10.f, 6.5f);

	/** The arrow lies on the bow this far above the middle of the grip (on top of her fist), cm. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Pose")
	float NockAbove = 8.f;

	/** The quiver (SM_Archer.json "quiver", character space): the way its mouth points, and how far the mouth is from
	 *  the part's joint (cm); the hand reaches GrabAbove beyond that, where the fletchings stand. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Pose")
	FVector QuiverAxis = FVector(0.f, 0.32557f, 0.94552f);

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Pose")
	float QuiverMouth = 20.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Archer|Pose")
	float GrabAbove = 9.f;

private:
	enum class EPhase : uint8 { Rest, Reach, Nock, Draw, Hold, Loose };
	enum class EMode : uint8 { None, Actor, Ground };

	bool Setup(AVLKing* Unit);
	void TickHands(AVLKing* Unit, float Dt);
	void TickOrders(AVLKing* Unit, float Dt);
	void TickShot(AVLKing* Unit, float Dt);
	void Pose(AVLKing* Unit, float Dt);
	void Loose(AVLKing* Unit);
	void Approach(AVLKing* Unit, const FVector& At);
	/** Is the first stretch of a shot from there to At free (no wall or roof right in front of the bow)? */
	bool ClearShot(const AVLKing* Unit, const FVector& From, const FVector& At) const;
	/** The pull (cm/s2) on an arrow shot from From at To: what gives the arc ArcPeak, ArcPeakDistance and ArcGrowth
	 *  ask for at that distance over the ground, at most ArrowGravity. */
	float ShotGravity(const FVector& From, const FVector& To) const;
	FVector OrderTarget() const;
	void ShowArrow(bool bShow);

	// ---- the rig (found once): joints, and the figure's measures in its rest pose, cm, character space
	bool bSetup = false;
	bool bBroken = false;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> Chest;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> Head;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> ArmL;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> ForeL;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> ArmR;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> ForeR;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> HandR;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> Bow;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> StringU;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> StringL;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> ArrowJoint;
	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> Quiver;
	UPROPERTY(Transient)
	TObjectPtr<UStaticMeshComponent> ArrowMesh;
	// the same joints as nodes of the unit's pose buffer (AVLKing::RigWorld and the like): the pose is read and written there
	int32 iChest = -1, iHead = -1, iArmL = -1, iForeL = -1, iArmR = -1, iForeR = -1, iHandR = -1, iBow = -1, iStringU = -1, iStringL = -1, iArrow = -1, iQuiver = -1;

	FVector UpperL = FVector::ZeroVector;       // shoulder -> elbow
	FVector GripL = FVector::ZeroVector;        // elbow -> the middle of the bow's grip
	FVector UpperR = FVector::ZeroVector;
	FVector GripR = FVector::ZeroVector;        // elbow -> the middle of the right fist
	FVector BowAxis = FVector::UpVector;        // along the bow, to its upper limb
	FVector BowString = FVector::BackwardVector;    // from the grip to the string, as modelled
	FVector BowStringCanted = FVector::BackwardVector;  // the same once the bow is turned in the fist (BowCant), in the forearm
	FVector StringEndU = FVector::ZeroVector;   // in the bow: where each half of the string leaves its limb, and their middle
	FVector StringEndL = FVector::ZeroVector;
	FVector StringMid = FVector::ZeroVector;
	FQuat StringFixU = FQuat::Identity;         // turns the half's own length onto its joint's Z (so it can be stretched)
	FQuat StringFixL = FQuat::Identity;
	FQuat BowRestFrame = FQuat::Identity;       // the bow's axes in the forearm (inverse)
	float MeshYaw = -90.f;
	float BuiltCant = -1000.f;

	// ---- a shot
	EPhase Phase = EPhase::Rest;
	float PhaseTime = 0.f;
	bool bQuick = false;
	bool bWantDraw = false;         // the string is to be drawn and held
	bool bLooseQueued = false;      // ... and loosed as soon as it is fully drawn (and she faces her aim)
	float HoldTime = 0.f;
	float AimW = 0.f;               // 0 the bow carried .. 1 the bow arm out at the aim
	float HandW = 0.f;              // 0 the right arm as the figure has it .. 1 on the arrow
	float AimPitch = 0.f;           // degrees the shot is raised, as shown
	FVector AimPoint = FVector::ZeroVector;
	bool bHasAim = false;
	FVector ArrowTip = FVector::ZeroVector;     // the arrow in her hand, as last posed
	FVector ArrowWay = FVector::ForwardVector;
	bool bArrowShown = true;
	bool bStringDrawn = false;      // the string was off its straight line last frame
	int32 Shots = 0;

	// ---- the player's hands
	bool bBattle = false;
	bool bHands = false;            // last frame: was she the unit the player plays
	bool bTestDraw = false;
	bool bWasHeld = false;          // the right button drew the bow last frame
	bool bWasRight = false;         // the right button was down last frame
	bool bLocked = false;           // the draw is locked (a left click while drawing): it stays until the next right press looses it
	bool bLetDown = true;           // the right button does nothing until it has been let go (after a let-down, a locked shot, taking her over, the menu)
	float BashTime = -1.f;          // seconds into a blow with the bow, or < 0
	bool bBashLanded = false;
	void Bash(AVLKing* Unit);
	FVector TestAim = FVector::ZeroVector;
	float TestAimTime = 0.f;
	FVector TestLook = FVector::ZeroVector;
	float TestLookTime = 0.f;

	// ---- orders
	EMode Mode = EMode::None;
	TWeakObjectPtr<AActor> Target;
	FVector GroundTarget = FVector::ZeroVector;
	FVector ShotScatter = FVector::ZeroVector;
	int32 ShotsLeft = -1;
	bool bOrderRun = false;
	bool bEngaged = false;
	bool bApproaching = false;
	bool bInternalOrder = false;    // the walk into range is her own order: it must not end the attack
	int32 Approaches = 0;
	float Cooldown = 0.f;
};
