#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "VLCommand.generated.h"

class AVLKing;

/** How a group stands at the end of a move (the main game's ESRFormationShape). */
UENUM()
enum class EVLFormation : uint8
{
	Line,       // ranks wider than deep, facing the way they came: melee in front, archers behind
	Column,     // two or three abreast
	Wedge,      // 1, 3, 5, ... from the point back
	Square,
	Loose       // no formation: each keeps its place in the group
};

/**
 * Commanding units from the overview: the selection, the platoons, group moves in formation, and the watch tower's
 * garrison. The ideas are the main game's (SRPlayerController's selection and IssueMove, SRPlatoonSubsystem,
 * SRFormation, USRBattleSubsystem::CommandMove), reimplemented on this sandbox's units (AVLKing and its troops) and
 * its path grid (UVLGrid). It lives in the world, not in a pawn, so it carries over when the player takes control of
 * another unit.
 *
 *   click / shift-click / drag a box      select / add or take out / all in the box
 *   right click on the ground             the selection goes there, forming up in its formation
 *   right click on the watch tower        the archers of the selection man its lookout (others wait at its door)
 *   click on a training dummy             the fighters of the selection attack it (Shift: at a run)
 *   Ctrl|Cmd|Alt + 1..6, 1..6, Shift + 1..6    make / select / add to platoon N
 *   F                                     the next formation (of the selected platoon, or of loose selections)
 */
UCLASS()
class VOXELLAB_API UVLCommand : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	static UVLCommand* Get(const UObject* WorldContext);
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

	// ---- selection
	void GetSelection(TArray<AVLKing*>& Out) const;
	int32 NumSelected() const;
	bool IsSelected(const AVLKing* Unit) const;
	void Select(const TArray<AVLKing*>& Units, bool bAdd = false);
	void Toggle(AVLKing* Unit);
	void ClearSelection() { Selection.Reset(); }

	// ---- orders
	/** The units go to a point of the ground, round whatever is in the way, and form up there. */
	/** bQueue (Shift + right click, as in the main game): units already on an order walk there after it, a point of
	 *  their pathway; idle ones start at once. Otherwise the order replaces whatever they were doing. */
	void OrderMove(const TArray<AVLKing*>& Units, const FVector& Ground, bool bRun, EVLFormation Shape, bool bQueue = false);
	/** The selection's formation: its platoon's if it is exactly one platoon, else the one loose selections use. */
	EVLFormation SelectionFormation() const;
	void CycleFormation();
	static const TCHAR* FormationName(EVLFormation Shape);
	bool SetFormationByName(const FString& Name);

	// ---- attacks. The part every kind of fighter shares: which dummy a click is on, and handing an attack order to
	// the selected units. The fighting itself is each kind's own combat component (swordsmen: UVLSwordsmanCombat,
	// VLSwordsmanCombat.*; archers: VLArcherCombat.*): add a kind in CanAttack, OrderAttack and StopAttack.
	/** Every training dummy (an actor tagged Dummy), sorted by name. */
	void GetDummies(TArray<AActor*>& Out) const;
	/** The training dummy drawn under a point of the viewport (the nearest to the camera), or null. */
	AActor* DummyAt(const class APlayerController* PC, const FVector2D& Point) const;
	/** Can this unit fight on orders? */
	static bool CanAttack(const AVLKing* Unit);
	/** Those of Units that can fight go and attack Target (a dummy) until they get another order; the others are
	 *  left as they are. Returns how many were ordered. */
	int32 OrderAttack(const TArray<AVLKing*>& Units, AActor* Target, bool bRun);
	/** The unit drops the attack it was ordered to (OrderMove does this: any other order ends an attack). */
	void StopAttack(AVLKing* Unit);
	/** Attack-ground (archers only): A in the overview arms it, if the selection has archers; the next left click on
	 *  the ground has them shoot at that spot a few times (UVLArcherCombat::GroundShots). It lapses after
	 *  AttackGroundSeconds, on a right click, or with the click. */
	void ArmAttackGround(bool bArm);
	bool IsAttackGroundArmed() const;
	static constexpr float AttackGroundSeconds = 5.f;
	/** The archers among Units shoot at that spot of the ground (walking into range first). Returns how many. */
	int32 OrderAttackGround(const TArray<AVLKing*>& Units, const FVector& Ground, bool bRun);

	// ---- platoons (1..6)
	static constexpr int32 MaxPlatoons = 6;
	void AssignPlatoon(int32 Index, const TArray<AVLKing*>& Units);
	void AddToPlatoon(int32 Index, const TArray<AVLKing*>& Units);
	void GetPlatoon(int32 Index, TArray<AVLKing*>& Out) const;
	EVLFormation PlatoonFormation(int32 Index) const { return Platoons[FMath::Clamp(Index, 0, MaxPlatoons - 1)].Formation; }
	/** The platoon these units are exactly the members of, or INDEX_NONE. */
	int32 PlatoonOf(const TArray<AVLKing*>& Units) const;
	/** "Swordsmen", "Archers", "Mixed host", ... from who is in it. */
	FString PlatoonName(int32 Index) const;
	FVector PlatoonCentre(int32 Index) const;

	// ---- the watch tower
	/** Does this building have a lookout archers can man (tag Lookout:..., from SM_WatchTower.json)? */
	static bool IsTower(const AActor* Building);
	/** The archers among Units walk to the tower's door and appear on its lookout; the others go and stand by the door. */
	void OrderGarrison(const TArray<AVLKing*>& Units, AActor* Tower, bool bRun);
	/** Everyone on the lookout comes down and forms up in front of the door. */
	void EmptyTower(AActor* Tower);
	int32 TowerCount(const AActor* Tower) const;
	int32 TowerCapacity(const AActor* Tower) const;
	void GetGarrison(const AActor* Tower, TArray<AVLKing*>& Out) const;
	/** Called by a unit when its order ends (it arrived, or gave up). */
	void OnOrderEnded(AVLKing* Unit, bool bArrived);

	// ---- feedback for the HUD: where the last orders went
	struct FMarker
	{
		FVector At;
		double Time;
	};
	const TArray<FMarker>& GetMarkers() const { return Markers; }
	static constexpr float MarkerSeconds = 0.7f;

private:
	struct FPlatoon
	{
		TArray<TWeakObjectPtr<AVLKing>> Members;
		EVLFormation Formation = EVLFormation::Line;
	};
	struct FTower
	{
		TWeakObjectPtr<AActor> Actor;
		TArray<TWeakObjectPtr<AVLKing>> Posts;      // who stands at each post of the lookout (or is on the way to it)
	};
	FTower& TowerFor(AActor* Tower);
	const FTower* FindTower(const AActor* Tower) const;
	bool PostWorld(const AActor* Tower, int32 Post, FVector& OutFeet, FRotator& OutFacing) const;
	/** Ground by the tower's door, on the town's own ground. */
	FVector DoorPoint(const AActor* Tower) const;
	void Enter(AVLKing* Unit, AActor* Tower);
	/** Down from the lookout, to the door (or as near it as there is room). */
	void Leave(AVLKing* Unit);
	void Detach(AVLKing* Unit);
	void AddMarker(const FVector& At);

	TArray<TWeakObjectPtr<AVLKing>> Selection;
	FPlatoon Platoons[MaxPlatoons];
	EVLFormation LooseFormation = EVLFormation::Line;
	TArray<FTower> Towers;
	TArray<FMarker> Markers;
	double AttackGroundArmedAt = -1.0;
};

namespace VLFormation
{
	/** The main game's SRFormation::ComputeSlots: a destination slot for every unit, in the same order as Units. */
	void ComputeSlots(const TArray<AVLKing*>& Units, const FVector2D& Destination, TArray<FVector2D>& OutSlots, EVLFormation Shape);
}
