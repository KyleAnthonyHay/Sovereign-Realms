#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "VLKing.generated.h"

class USpringArmComponent;
class UCameraComponent;
class UStaticMeshComponent;
class UVLCharacterData;
class ACameraActor;
class UMaterialInstanceDynamic;
class UVLFootDust;

/** What a foot comes down on: which set of step sounds plays (S_Step_<Surface>_<n>). */
UENUM()
enum class EVLStepSurface : uint8
{
	Dirt,       // grass, earth, farm soil, the yards
	Cement,     // stone, cobble, gravel, the castle steps, the plaza
	Wood,       // the bridge, the dock, planks, decks, the tower's lookout
	Carpet      // soft: the shuffle of marching troops (AVLGameMode)
};

/** The recorded steps of one surface, and which was played last (never the same twice running). */
USTRUCT()
struct FVLStepSet
{
	GENERATED_BODY()

	UPROPERTY(Transient)
	TArray<TObjectPtr<class USoundBase>> Sounds;
	int32 Last = -1;
	bool bLoaded = false;

	/** /Game/Voxel/Audio/S_Step_<Surface>_1.. (loaded at the first call), one picked at random; null if none. */
	class USoundBase* Pick(EVLStepSurface Surface, int32* OutIndex = nullptr);
};

/**
 * King David, and the two ways of playing the sandbox.
 *
 * HERO: the camera follows him at the diorama angle. WASD / left stick walk (relative to the view), Shift runs, Space
 * jumps, F draws or sheathes the sword, left click attacks (drawing first if need be): the training dummies take the blows.
 * OVERVIEW: a bird's-eye camera that pans freely with WASD. Left click selects the king or a building (click the
 * ground to deselect); with the king selected a right click sends him there, and Enter or a double click takes control.
 * Both: wheel zooms (the view steepens as it pulls back), Q / E or a right-button drag turn the view, R turns it back,
 * Tab switches between the two, C shows the postcard view, Esc the menu.
 *
 * He is a voxel figure of rigid parts, jointed like a wooden toy (waist, neck, shoulders, elbows, the sword hand's
 * wrist, hips, knees) and posed in code each frame (Animate): a gait whose feet are placed by a two-bone solver, a jump
 * with its own airborne pose and a sprung landing, a whole-body sword swing through four key poses, and a cape of hinged
 * panels swung as cloth (UpdateCape). Being hurt (ReceiveDamage) flashes him white and holds his pose for a moment
 * while the game carries on. Where a tree or a building hides him his silhouette shows through (custom depth +
 * M_Silhouette).
 */
UCLASS()
class VOXELLAB_API AVLKing : public ACharacter
{
	GENERATED_BODY()

public:
	AVLKing();

	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

	/** Walks there by himself (vl.Walk, or an order from the overview), until the player takes the controls: by a
	 *  route round whatever is in the way (UVLGrid), not in a straight line. */
	void WalkTo(const FVector2D& Target, bool bRun);
	/** An order: visit these points in turn (corners of a route, the last one where it stands at the end). */
	void FollowPath(const TArray<FVector>& Points, bool bRun);
	/** Drops the order it is on (it stops where it is). */
	void StopOrder();
	bool HasOrder() const { return bAutoWalk; }
	const TArray<FVector>& GetWaypoints() const { return Waypoints; }
	/** The point of the ground under it. */
	FVector GetFeet() const;
	/** An archer: stands behind the melee in a formation, and can man the watch tower. */
	bool IsRanged() const { return UnitKind == TEXT("Archer"); }
	const FString& GetKind() const { return UnitKind; }
	void SetKind(const FString& InKind) { UnitKind = InKind; }
	bool IsGarrisoned() const { return GarrisonIn.IsValid(); }
	/** The tower whose lookout it stands on, and the one it is walking to (UVLCommand keeps both). */
	TWeakObjectPtr<AActor> GarrisonIn;
	TWeakObjectPtr<AActor> PendingGarrison;
	/** The box being dragged in the overview (viewport points), if any. */
	bool GetSelectionBox(FVector2D& A, FVector2D& B) const { A = PressPos; B = DragPos; return bBoxing; }
	void SetOrbit(float Yaw, float Pitch, float Distance);
	/** The follow camera trails him a little (on by default); off, he stays dead centre (for motion previews). */
	void SetCameraLag(bool bLag);
	/** As if W/S (Forward) and D/A (Right) were held for a while: for testing (vl.Move). */
	void TestInput(float Forward, float Right, float Seconds, bool bRun = false) { TestMove = FVector2D(Forward, Right); TestMoveTime = Seconds; bTestRun = bRun; }
	/** 0 hero camera, 1 postcard camera, 2 free camera, 3 overview camera. */
	void SetView(int32 Mode, float Blend = 0.6f);
	void SetFreeCamera(const FVector& Location, const FRotator& Rotation, float FOV);
	void SetHeroMode(bool bHero);
	/** The overview, over a point (vl.Look). Zoom < 0 and Yaw = max keep what they are. */
	void LookAt(const FVector& Point, float InZoom, float InYaw);
	void SetArmed(bool bDrawn) { bArmed = bDrawn; }
	/** One swing. In the battle stance each further call is the next of the combo: side slash, diagonal cut, up-down-up. */
	void Attack(int32 Kind = -1);

	/** Confirmed damage: he flashes white (HitFlashSeconds) and his pose holds still for HitPauseSeconds. Only what is
	 *  seen pauses: input, movement, gravity, collision and the swing's own timing carry on, nothing is cancelled, and
	 *  the pose then catches up with the game. Amounts of zero or less do nothing. */
	UFUNCTION(BlueprintCallable, Category = "Voxel")
	void ReceiveDamage(float Amount, AActor* From = nullptr);

	virtual float TakeDamage(float DamageAmount, const FDamageEvent& DamageEvent, AController* EventInstigator, AActor* DamageCauser) override;

	float GetHealth() const { return Health; }

	/** "king", a unit's name ("Swordsman 2"), the name of a selectable building ("Town Hall"), or anything else to
	 *  clear the selection (vl.Select). */
	void SelectByName(const FString& Name);

	/** Hands the player's controls to another unit (the king or a troop): it gets the hero camera, this one an AI
	 *  controller that walks it to orders. Enter / a double click in the overview, or vl.Control. */
	void TakeControlOf(AVLKing* Unit);

	/** A troop (AVLTroop): commanded from the overview, no footstep dust. The swordsman swings his sword as the king
	 *  does (it is always in his hand: nothing to draw); on orders through UVLSwordsmanCombat. */
	bool IsTroop() const { return bTroop; }
	const FString& GetDisplayName() const { return DisplayName; }
	void SetDisplayName(const FString& Name) { DisplayName = Name; }
	void SetCharacterData(const TSoftObjectPtr<UVLCharacterData>& InData) { Data = InData; }

	bool IsHeroMode() const { return bHeroMode; }
	bool IsWalkingTo() const { return bAutoWalk; }
	bool IsArmed() const { return bArmed; }
	/** In the middle of a swing. */
	bool IsSwinging() const { return AttackTime >= 0.f; }
	AActor* GetSelected() const { return Selected.Get(); }
	FString GetSelectedName() const;

	UPROPERTY(EditAnywhere, Category = "Voxel")
	TSoftObjectPtr<UVLCharacterData> Data;

	UPROPERTY(EditAnywhere, Category = "Voxel")
	FString DisplayName = TEXT("King David");

	UPROPERTY(EditAnywhere, Category = "Voxel")
	bool bTroop = false;

	/** "King", "Swordsman", "Archer". */
	UPROPERTY(EditAnywhere, Category = "Voxel")
	FString UnitKind = TEXT("King");

	UPROPERTY(EditAnywhere, Category = "Voxel")
	float WalkSpeed = 420.f;

	UPROPERTY(EditAnywhere, Category = "Voxel")
	float RunSpeed = 760.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Damage")
	float MaxHealth = 100.f;

	/** How long his pose holds still when he is hurt (seconds; 0 = no pause). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Damage")
	float HitPauseSeconds = 0.07f;

	/** How long the white flash lasts: full for the first HitFlashHold of it, then fading. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Damage")
	float HitFlashSeconds = 0.16f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Damage")
	float HitFlashHold = 0.4f;

	/** How white the flash is at its height (0..1). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Damage")
	float HitFlashStrength = 0.92f;

	/** After the pause the pose runs this much faster than the game until it has caught up (0.5 = half as fast again). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Damage")
	float HitCatchUp = 0.5f;

	/** Landing: how far he sinks per cm/s of fall speed (0..1 of LandDepth), how deep at most (cm), how fast the knees
	 *  spring back (rad/s) and how damped (1 = no overshoot). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Motion")
	float LandImpulse = 0.036f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Motion")
	float LandDepth = 15.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Motion")
	float LandSpring = 13.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Motion")
	float LandDamping = 0.8f;

	/** Running: forward lean of the chest (degrees) and how far the elbows bend (degrees). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Motion")
	float RunLean = 21.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Motion")
	float RunElbow = 92.f;

	/** The cape. Trail: degrees it streams back per cm/s of speed. Inertia: degrees per cm/s2 of acceleration. Fall:
	 *  degrees it lifts per cm/s of falling. Stiffness (rad/s) at the top row and at the hem, Damping (1 = no swing
	 *  past rest), Flutter (degrees at a run), YawLag (how fast each row follows the turn of the one above, 1/s). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Cape")
	float CapeTrail = 0.04f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Cape")
	float CapeInertia = 0.007f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Cape")
	float CapeFall = 0.03f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Cape")
	float CapeStiffTop = 13.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Cape")
	float CapeStiffHem = 8.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Cape")
	float CapeDamping = 0.42f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Cape")
	float CapeFlutter = 4.5f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Cape")
	float CapeYawLag = 16.f;

	/** Hero camera: distance (cm) and pitch (degrees) fully zoomed in and fully zoomed out. (The far end was 5200
	 *  at -38: it now runs 1.4 times further along the same curve, and a wheel step is 1 / 1.4 of what it was, so the
	 *  old range feels as it did.) */
	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	float ArmNear = 650.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	float ArmFar = 9500.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	float PitchNear = -20.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	float PitchFar = -45.f;

	/** One notch of the mouse wheel, as a share of the whole zoom range (both views). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	float ZoomStep = 0.05f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	float CameraFOV = 40.f;

	/** Overview camera. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	float OverviewNear = 2400.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	float OverviewFar = 19500.f;        // (was 11000 at -40: 1.4 times further along the same curve)

	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	float OverviewPitchNear = -26.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	float OverviewPitchFar = -46.f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	float OverviewFOV = 30.f;

	/** Camera angle, both views (as the main game's setting): 0 Classic (steep: the pitches above), 1 Low,
	 *  2 Battlefield (shallow). V or the Esc menu cycles it; it is saved in GameUserSettings. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	int32 CameraAngle = 0;

	float HeroPitch(float InZoom) const;
	float OverviewPitch(float InZoom) const;
	void CycleCameraAngle();
	int32 GetCameraAngle() const { return CameraAngle; }
	static const TCHAR* CameraAngleName(int32 Angle);

	UPROPERTY(VisibleAnywhere, Category = "Voxel")
	TObjectPtr<USpringArmComponent> Boom;

	UPROPERTY(VisibleAnywhere, Category = "Voxel")
	TObjectPtr<UCameraComponent> Camera;

	UPROPERTY(VisibleAnywhere, Category = "Voxel")
	TObjectPtr<USceneComponent> Figure;

	/** The dust his feet raise at a run, and when he lands or brakes hard (its own knobs: puffs per step, size,
	 *  lifetime, colour). Off: bFootDust. */
	UPROPERTY(VisibleAnywhere, Category = "Voxel")
	TObjectPtr<UVLFootDust> Dust;

	/** A swing (left click) turns him to face the pointer for FaceMouseHoldSeconds (WASD strafes meanwhile); then he
	 *  turns back to his way of walking. The King and played swordsmen (archers aim with their own component). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Motion")
	bool bFaceMouseWhenArmed = true;

	UPROPERTY(EditAnywhere, Category = "Voxel|Motion")
	float FaceMouseHoldSeconds = 1.5f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Motion")
	float FaceMouseTurnRate = 900.f;

	float FaceMouseLeft = 0.f;
	float FaceYaw = 0.f;
	/** The yaw a swing faces: the crosshair's way while mouse-looking (to GetAimPoint, never back towards the
	 *  camera), else from him to where the mouse pointer meets the ground at his feet. */
	bool PointerYaw(APlayerController* PC, float& OutYaw) const;

	/** Hero view: the mouse looks round (X turns, Y tilts up and down; the pointer is hidden and a crosshair shows
	 *  where he aims). The overview, the postcard view and the menu show the pointer as before. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	bool bMouseLook = true;

	/** Mouse-look speed at 100% of the setting (75% = 0.9, the first speed tried). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	float MouseLookSpeed = 1.2f;

	/** The player's setting (Esc menu / L): 25%..150%, saved. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	float LookSpeedSetting = 0.5f;

	/** Fully zoomed out the mouse looks this much slower than fully zoomed in (a straight blend between). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	float LookSpeedFar = 0.45f;

	void CycleLookSpeed();

	/** Invert look (Esc menu / I): bit 1 left-right, bit 2 up-down; saved. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	int32 LookInvert = 0;

	void CycleLookInvert();
	int32 GetLookInvert() const { return LookInvert; }
	static const TCHAR* LookInvertName(int32 Invert);
	float GetLookSpeedSetting() const { return LookSpeedSetting; }
	float CaptureRetry = 0.f;


	/** Where the crosshair sits on the screen, from the top (0..1): aims land where its ray meets the world. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Camera")
	float CrosshairHeight = 0.36f;

	bool IsMouseLooking() const { return bMouseLookActive; }
	/** The ray aims follow: through the crosshair while mouse-looking, else through the pointer. */
	bool GetAimRay(APlayerController* PC, FVector& Origin, FVector& Dir) const;
	/** The point an aim lands on: where the aim ray meets the world AHEAD. While mouse-looking the ray is only followed
	 *  from where it passes this unit onwards, so nothing between the camera and the unit (a tree, a roof, a fence
	 *  close to the lens) can catch it and turn the unit round; if it meets nothing within reach, a point SkyDistance
	 *  along the crosshair's way. With the pointer shown: what the pointer is over, else the ground at the unit's
	 *  feet. Units and the tree crowns the camera cuts away (actors tagged Canopy) never catch it. While mouse-looking
	 *  the point is always in front of the unit as the camera sees it. */
	bool GetAimPoint(APlayerController* PC, FVector& OutPoint, float SkyDistance = 3000.f) const;
	void UpdateCursorMode(APlayerController* PC, const class AVLHUD* HUD);
	float LookPitch = 0.f;
	bool bMouseLookActive = false;
	bool bCursorModeSet = false;

	UPROPERTY(EditAnywhere, Category = "Voxel|Motion")
	bool bFootDust = true;

	/** A step sound each time a foot of the gait comes down, from the recordings of the surface under that foot
	 *  (/Game/Voxel/Audio/S_Step_Dirt|Cement|Wood_<n>): a random one, never the same twice running. The hero only;
	 *  marching troops shuffle as a group (AVLGameMode). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Footsteps")
	bool bFootsteps = true;

	/** Volume of a step at a walk, and at a full run (in between while he speeds up). */
	UPROPERTY(EditAnywhere, Category = "Voxel|Footsteps")
	float FootstepWalkVolume = 0.32f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Footsteps")
	float FootstepRunVolume = 0.6f;

	/** Pitch at a full run (1 at a walk): higher is shorter and snappier. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Footsteps")
	float FootstepRunPitch = 1.1f;

	/** Each step's pitch is off by up to this share either way, and its volume down by up to FootstepVolumeJitter. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Footsteps")
	float FootstepPitchJitter = 0.06f;

	UPROPERTY(EditAnywhere, Category = "Voxel|Footsteps")
	float FootstepVolumeJitter = 0.15f;

	/** Material under the foot -> surface. The key is the material's name without its MI_Vox_ / MI_Sway_ prefix (the
	 *  voxel meshes' slot: grass, cobble, plank, ...); a material not listed takes the entry its name contains, if
	 *  any, else FootstepDefault. */
	UPROPERTY(EditAnywhere, Category = "Voxel|Footsteps")
	TMap<FName, EVLStepSurface> FootstepSurfaces;

	UPROPERTY(EditAnywhere, Category = "Voxel|Footsteps")
	EVLStepSurface FootstepDefault = EVLStepSurface::Dirt;

	/** The surface at a point of the floor (a short trace down, the material of the triangle hit). */
	EVLStepSurface SurfaceUnder(const FVector& Foot, FString* OutMaterial = nullptr) const;

	/** For components that pose parts of the figure themselves, after Animate (UVLArcherCombat): a part's joint by
	 *  its name, and the character's data. */
	USceneComponent* GetJoint(FName Name) const { return Part(Name); }
	UVLCharacterData* GetCharacterData() const { return Loaded; }
	/** Set by UVLArcherCombat while the player plays an archer: she moves no faster than this (cm/s; 0 = no limit)
	 *  while she draws, and the right mouse button draws her bow instead of turning the camera. */
	float MoveSpeedCap = 0.f;
	bool bRightMouseAims = false;

	/** Where the player's attention is: the unit in hero mode, the point the overview looks at otherwise. */
	FVector GetListenFocus() const { return bHeroMode ? GetActorLocation() : OverviewFocus; }

	/** What is under the mouse: the king, a selectable building, or nothing. Ground receives the point hit, if any. */
	AActor* PickUnderCursor(APlayerController* PC, FVector* Ground = nullptr) const;
	/** The same, under a point of the viewport. */
	AActor* PickAt(APlayerController* PC, const FVector2D& Point, FVector* Ground = nullptr) const;
	/** What the mouse does in the overview, at a point of the viewport (also vl.Click / vl.Box / vl.RightClick):
	 *  a click selects the unit or building there (Shift: adds the unit or takes it out) or, on a training dummy,
	 *  has the selection's fighters attack it (UVLCommand::OrderAttack; Shift: at a run), a box every unit in it,
	 *  a right click sends the selection there or, on the watch tower, has its archers man it. */
	/** True if the click gave an attack order (it was on a training dummy, with fighters selected). */
	bool ClickAt(const FVector2D& Point, bool bShift);
	void BoxSelect(const FVector2D& A, const FVector2D& B, bool bShift);
	/** True if an order was given. */
	bool OrderAt(const FVector2D& Point, bool bRun, bool bQueue = false);

	/** Its pathway (Shift + right click): points walked one after another once the current order is done. */
	void QueueLeg(const FVector& Slot, bool bRun);
	void ClearQueue();
	bool IsOnOrder() const { return bAutoWalk || QueuedLegs.Num() > 0; }
	/** What is left of its way (for the HUD): the corners of the route it is walking, and where each leg ends (the
	 *  current order's goal, then its queued points). */
	void GetPathway(TArray<FVector>& OutRoute, TArray<FVector>& OutLegs) const
	{
		OutRoute = bAutoWalk ? Waypoints : TArray<FVector>();
		OutLegs.Reset();
		if (bAutoWalk)
		{
			OutLegs.Add(OrderGoal);
		}
		OutLegs.Append(QueuedLegs);
	}

private:
	void BuildFigure();
	void HitDummies();
	void StartSwing(int32 Kind);
	/** Dt: the game's time (the swing's and the draw's own clocks). AnimDt: the time the pose moves on by (0 while a hit holds it). */
	void Animate(float Dt, float AnimDt);
	void UpdateSword(const float* Pose, float AnimDt);
	void UpdateCape(float AnimDt);
	void UpdateFlash(float Dt);
	void PollInput(float DeltaSeconds);
	void UpdateOverviewCamera(float DeltaSeconds, bool bSnap = false);
	USceneComponent* Part(FName Name) const;

	UPROPERTY(Transient)
	TObjectPtr<UVLCharacterData> Loaded;

	UPROPERTY(Transient)
	TMap<FName, TObjectPtr<USceneComponent>> Joints;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> Meshes;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> FlashMID;

	UPROPERTY(Transient)
	TObjectPtr<USceneComponent> SwordJoint;

	UPROPERTY(Transient)
	TObjectPtr<ACameraActor> FreeCamera;

	UPROPERTY(Transient)
	TObjectPtr<ACameraActor> OverviewCamera;

	// the joints (owned through Joints) and the measures of the figure, cm, character space
	struct FRig
	{
		USceneComponent* Body = nullptr;
		USceneComponent* Chest = nullptr;
		USceneComponent* Head = nullptr;
		USceneComponent* ArmL = nullptr;
		USceneComponent* ForeL = nullptr;
		USceneComponent* ArmR = nullptr;
		USceneComponent* ForeR = nullptr;
		USceneComponent* HandR = nullptr;
		USceneComponent* LegL = nullptr;
		USceneComponent* ShinL = nullptr;
		USceneComponent* LegR = nullptr;
		USceneComponent* ShinR = nullptr;
		FVector HipL = FVector::ZeroVector, HipR = FVector::ZeroVector;      // in the figure
		float Thigh = 32.f, Shin = 35.f;
		FVector ShoulderR = FVector::ZeroVector;                              // in the chest
		FVector UpperR = FVector::ZeroVector, ForeVecR = FVector::ZeroVector; // shoulder -> elbow -> wrist at rest
		FVector ForeAxis = FVector(0.f, 0.f, -1.f);                           // down the forearm
		FVector Blade = FVector::ForwardVector;                               // the blade as modelled in the fist
		FVector GripOff = FVector::ZeroVector;                                // wrist -> the middle of the grip
		float HipHeight = 67.f;
	};
	FRig Rig;

	// the cape: every column a chain of panels, each swung about the hinge at its top edge
	static constexpr int32 CapeMaxCols = 6;
	static constexpr int32 CapeMaxRows = 5;
	struct FCapePanel
	{
		USceneComponent* Joint = nullptr;
		float Length = 25.f;
		float Slope = 0.f;                   // degrees it hangs away from him at rest
		float Pitch = 0.f, PitchVel = 0.f;   // degrees back from its rest hang, in the actor's frame
		float Roll = 0.f, RollVel = 0.f;
		float Yaw = 0.f;                     // relative to the actor: follows the chest's turn, row after row
		FVector Prev = FVector::ZeroVector;
		FVector Vel = FVector::ZeroVector;
		FVector Acc = FVector::ZeroVector;
	};
	FCapePanel Cape[CapeMaxCols][CapeMaxRows];
	int32 CapeCols = 0, CapeRows = 0;
	bool bCapeStarted = false;
	float CapeTime = 0.f;
	float CapeBackUpper = -100.f, CapeBackLower = -100.f;   // how far back his body reaches (actor space, cm forward): the cape stays behind it

	FVector2D TestMove = FVector2D::ZeroVector;
	float TestMoveTime = 0.f;
	bool bTestRun = false;
	float Phase = 0.f;
	float Gait = 0.f;          // 0 standing .. 1 walking .. 2 running, smoothed
	float IdleTime = 0.f;
	float Air = 0.f;           // 0 on the ground .. 1 airborne, smoothed
	float Rise = 0.f;          // -1 falling fast .. 1 rising fast, smoothed
	float Crouch = 0.f;        // the landing: 0..1 of LandDepth, a damped spring
	float CrouchVel = 0.f;
	float LastFallSpeed = 0.f;
	bool bWasFalling = false;
	bool bLeadLeft = false;    // which knee leads in the air
	FVector KneeBack = FVector::ZeroVector;    // x: the rearmost knee or heel, figure space (for the cape)
	bool bFootDown[2] = { true, true };        // was each foot on the ground last frame (left, right)
	float LastSpeed = 0.f;
	float SkidTimer = 0.f;

	// being hurt
	float Health = 100.f;
	float HitPauseLeft = 0.f;  // seconds the pose still holds
	float AnimLag = 0.f;       // seconds the pose is behind the game
	float FlashLeft = 0.f;
	bool bFlashOn = false;

	// hero camera: the diorama view of the reference picture
	float CamYaw = -62.f;      // set from the postcard camera at BeginPlay
	float HomeYaw = -62.f;
	float Zoom = 0.3f;        // 0 close .. 1 far: distance and pitch both follow it
	float ManualPitch = 0.f;   // vl.Orbit can pin the pitch and distance (0 = follow the zoom)
	float ManualArm = 0.f;
	float TargetArm = 1500.f;
	int32 ViewMode = 0;

	// overview
	bool bHeroMode = true;
	FVector OverviewFocus = FVector::ZeroVector;
	float OverviewYaw = -62.f;
	float OverviewZoom = 0.355f;
	TWeakObjectPtr<AActor> Selected;
	TWeakObjectPtr<AActor> LastClicked;
	double LastClickTime = 0.0;
	FVector2D RightDownAt = FVector2D::ZeroVector;
	float RightTravel = 0.f;

	// sword. It is modelled in his fist and stays rigid in it: the blade is aimed by posing the arm and turning the
	// wrist (about the forearm freely, sideways within what a wrist can do).
	FQuat WristQ = FQuat::Identity;
	bool bArmed = false;
	float Draw = 0.f;          // 0 in the scabbard .. 1 in his hand (the game's clock: the queued swing waits for it)
	float DrawVis = 0.f;       // the same, as shown
	float Guard = 0.f;         // 0 regular stance .. 1 battle stance
	float GuardHold = 0.f;     // seconds of battle stance left after the last swing
	float RestingArmed = 0.f;  // seconds he has stood with it drawn in the regular stance (sheathes at SheatheAfter)
	FVector FigureRest = FVector::ZeroVector;
	float AttackTime = -1.f;   // seconds into a swing, or < 0 (the game's clock: the hit lands by it)
	float SwingTime = -1.f;    // the same, as shown
	bool bAttackQueued = false;
	/** Which swing: 0 the side slash, 1 the diagonal cut, 2 up-down-up. Clicks while he is in the battle stance go on
	 *  through them in turn; once the stance has lapsed the next click starts at the side slash again. */
	int32 SwingKind = 0;
	int32 HitsLanded = 0;      // blows of this swing that have landed
	bool bComboQueued = false; // clicked during a swing: the next one follows on
	bool bSwingCarry = false;  // this swing follows on from another: it starts from that one's pose
	float SwingShown[40] = {}; // the swing's pose as last shown, and the one a following swing started from
	float SwingCarry[40] = {};

	bool bAutoWalk = false;
	bool bAutoRun = false;
	// an order: the corners still to visit; how it is getting on (a unit that stops making way plans afresh)
	TArray<FVector> Waypoints;
	FVector OrderGoal = FVector::ZeroVector;
	FVector2D ProgressAt = FVector2D::ZeroVector;
	float ProgressTime = 0.f;
	int32 StuckCount = 0;
	int32 Replans = 0;
	/** The way to walk this frame on the order it has; false: it has none (any more). */
	bool AutoSteer(float DeltaSeconds, FVector& OutWish);
	void FinishOrder(bool bArrived);
	// fallen in the water: back to where it last stood on walkable ground
	FVector LastSafe = FVector::ZeroVector;
	bool bHasSafe = false;
	float SafeTimer = 0.f;
	float WetTime = 0.f;
	void UpdateSafety(float DeltaSeconds);
	// overview: a click or a dragged box, the platoon keys
	bool bLeftDown = false;
	bool bBoxing = false;
	FVector2D PressPos = FVector2D::ZeroVector;
	FVector2D DragPos = FVector2D::ZeroVector;
	int32 LastPlatoonKey = -1;
	double LastPlatoonTime = -1.0;
	void OverviewCommands(APlayerController* PC, class AVLHUD* HUD, bool bRun);
	void PlayFootstep(const FVector& At, float RunBlend);
	UPROPERTY(Transient)
	FVLStepSet StepSets[3];     // Dirt, Cement, Wood
	TArray<FVector> QueuedLegs;
	TArray<bool> QueuedRuns;
	bool StartNextLeg();
	double LastOrderClickTime = -1.0;
	FVector2D LastOrderClickPos = FVector2D::ZeroVector;
	float AutoTime = 0.f;       // seconds on the current order, and when it gives up (blocked)
	float AutoGiveUp = 10.f;

	// double-tap a direction to run
	int32 LastTapKey = -1;
	double LastTapTime = -1.0;
	bool bTapRun = false;
	static constexpr double DoubleTapSeconds = 0.3;
	FVector2D AutoTarget = FVector2D::ZeroVector;
};
