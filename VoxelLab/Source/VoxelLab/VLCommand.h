#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "VLKing.h"
#include "VLCommand.generated.h"

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

/** What the next left click in the overview does (a key or a command-card button arms it). */
UENUM()
enum class EVLArm : uint8
{
	None,
	AttackGround,   // A (archers): they shoot at the spot clicked
	AttackMove,     // A: march there, fighting what they meet (Shift + click: one more point of the way)
	Patrol,         // P: between where they stand and there (Shift + click: one more point of the loop)
	Guard           // V: the building, Builder or King David clicked
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
 *
 * STANDING ORDERS (the main game's Stop, Hold, Patrol, Guard, Roam, attack-move, March together, Dismiss). These are
 * the calls for any commander, the player's input and the enemy's AI alike; each takes the units it is for and
 * replaces whatever they were doing:
 *   OrderStop(Units)                      drop every order; stand (they still answer foes by their stance)
 *   OrderHold(Units)                      stand fast until the next order: strike only what is already in reach
 *   OrderPatrol(Units, Points, ...)       walk from where they stand through Points and back, round and round,
 *                                         fighting what they meet; ExtendPatrol adds a point to a patrol under way
 *   OrderAttackMove(Units, Ground, ...)   march there fighting what they meet, and march on after each fight
 *   OrderGuard(Units, Ward)               posts in a ring round a building, a Builder or King David of their side;
 *                                         they fight what comes within GuardLeash of it, and the order ends when it falls
 *   OrderRoam(Units)                      the Spies among them wander on their own; struck, a Spy runs home
 *   Dismiss(Units)                        troops removed for good (no refund)
 * Any other order (OrderMove, OrderAttack, OrderAttackGround, OrderGarrison) ends a standing order; the units' own
 * fights on the way (UVLBattle's), an archer walking into range and a defensive unit's walk back to its post do not
 * (they run with bInnerOrder set). TickOrders (from UVLBattle::Tick) walks the patrols, keeps guards at their posts
 * and moves the roamers on.
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
	/** Is it in a fight it was ordered into (not one of its own accord)? */
	static bool IsInOrderedFight(const AVLKing* Unit);
	/** Those of Units that can fight go and attack Target (a dummy) until they get another order; the others are
	 *  left as they are. Returns how many were ordered. */
	int32 OrderAttack(const TArray<AVLKing*>& Units, AActor* Target, bool bRun, bool bMarker = true);
	/** A unit fell (UVLBattle): out of the selection, its platoon and the tower. */
	void OnUnitDied(AVLKing* Unit);
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

	// ---- standing orders (see the class comment)
	void OrderStop(const TArray<AVLKing*>& Units);
	void OrderHold(const TArray<AVLKing*>& Units);
	/** Points: one or more points of the ground (world cm); the patrol starts where the group stands. */
	void OrderPatrol(const TArray<AVLKing*>& Units, const TArray<FVector>& Points, bool bRun = false, EVLFormation Shape = EVLFormation::Line);
	/** One more point on the patrol these units are on together (a new patrol from where they stand if none). */
	void ExtendPatrol(const TArray<AVLKing*>& Units, const FVector& Point, EVLFormation Shape = EVLFormation::Line);
	/** bQueue: one more point of the attack-move these units are on together (Shift + click). */
	void OrderAttackMove(const TArray<AVLKing*>& Units, const FVector& Ground, bool bRun = false, EVLFormation Shape = EVLFormation::Line, bool bQueue = false);
	/** Returns how many took a post (Builders do not guard; nobody guards itself). bTroops: Ward may be any living unit
	 *  of their side (the hero view's Option + click, V + click). Platoon: the guard is of that platoon: when Ward
	 *  falls it passes to the platoon's leader, else its nearest member, and ends only with the platoon. */
	int32 OrderGuard(const TArray<AVLKing*>& Units, AActor* Ward, bool bTroops = false, int32 Platoon = INDEX_NONE);
	/** The selection-style call for a whole platoon: its leader (else the member nearest its middle) is the ward, the
	 *  platoon's own members among Units are left out. Returns how many took a post. */
	int32 OrderGuardPlatoon(const TArray<AVLKing*>& Units, int32 Platoon);
	/** Can units of Team guard it: a standing building of theirs, or a living Builder or King of theirs; bTroops: any
	 *  living unit of theirs that can be ordered (not a tower's own archer). */
	bool CanBeGuarded(const AActor* Ward, int32 Team, bool bTroops = false) const;
	/** The platoon a guard was posted to (OrderGuardPlatoon), or INDEX_NONE. */
	int32 GuardPlatoonOf(const AVLKing* Unit) const;
	/** Every unit that the player's units guard (the HUD's shield over a ward). */
	void GetGuardedUnits(TArray<AVLKing*>& Out) const;
	/** Returns how many Spies set out. */
	int32 OrderRoam(const TArray<AVLKing*>& Units);
	/** Troops gone for good, quietly (no refund; the king cannot be dismissed). Returns how many. */
	int32 Dismiss(const TArray<AVLKing*>& Units);
	/** Units (Leader left out) fall in behind Leader in their formation and keep with it wherever it goes, re-sent
	 *  as it moves; they fight what they meet on the way and let go of a chase FollowLeash from it. Ends with any
	 *  other order, or when Leader falls. If the followers and Leader share a platoon, Leader becomes its leader.
	 *  Returns how many follow. */
	int32 OrderFollow(const TArray<AVLKing*>& Units, AVLKing* Leader, bool bMarker = true);
	/** The unit it follows (OrderFollow), if any. */
	AVLKing* FollowedBy(const AVLKing* Unit) const;
	/** Those following Leader (OrderFollow). */
	void GetFollowers(const AVLKing* Leader, TArray<AVLKing*>& Out) const;

	// ---- order chains: Shift + click on foes and the ground queues them (attack unit 1, then unit 2, then a building,
	// then walk there), for the selection or, in the hero view, those under the hero's command
	struct FChainItem
	{
		TWeakObjectPtr<AActor> Target;      // an attack: the foe's unit or building
		FVector Ground = FVector::ZeroVector;   // a walk: where to (an attack: where its target stood when queued)
		bool bAttack = false;
		bool bRun = false;
	};
	/**
	 * Units take an order: Target (a foe's unit or building: attack it) or a walk to Ground in Shape. Not bQueue: at
	 * once, in place of whatever they were doing (an attack is then the first item of their chain, so Shift adds to
	 * it). bQueue: on the end of the chain they are on; with none, a chain that starts once they are done with what
	 * they are doing (a walk, a fight they were ordered into; a patrol, guard or follow is ended). Items are done in
	 * turn: an attack once its target has fallen or been razed (or none of them is on it any more: out of reach), a
	 * walk once they are there. Rejoin: when the chain runs out after an attack, they fall in behind that unit
	 * (OrderFollow): the hero's followers commanded from his view. Returns true if anyone took it.
	 */
	bool OrderChain(const TArray<AVLKing*>& Units, AActor* Target, const FVector& Ground, bool bRun, EVLFormation Shape, bool bQueue, AVLKing* Rejoin = nullptr);
	/** Is it on a chain (its first order under way, or waiting for what it is doing)? */
	bool HasChain(const AVLKing* Unit) const;
	/** Every chain (the HUD's numbered markers): its living members, its items in order (the first under way if
	 *  bStarted), and whom it rejoins. */
	struct FChainView
	{
		TArray<AVLKing*> Members;
		TArray<FChainItem> Items;
		bool bStarted = false;
		AVLKing* Rejoin = nullptr;
		int32 Id = 0;
	};
	void GetChains(TArray<FChainView>& Out) const;
	static constexpr float FollowLeash = 2400.f;
	/** Ends whatever standing order these units are on (patrol, attack-move route, guard, hold, roam). */
	void ClearStanding(const TArray<AVLKing*>& Units);
	/** Walks the patrols and attack-moves, keeps guards at their posts, moves the roamers on (UVLBattle::Tick). */
	void TickOrders(float Dt);
	/** UVLBattle::Damage: a unit was struck (a roaming Spy runs home). */
	void OnStruck(AVLKing* Victim, AActor* By);
	/** Set while an order is given on the units' own account (TGuardValue): it does not end their standing orders. */
	bool bInnerOrder = false;
	/** cm round its ward a guard fights in (a foe that struck the ward or the guard: 1.8 times as far). */
	static constexpr float GuardLeash = 1800.f;
	// what a unit is on (the HUD, the AI)
	/** The thing it guards, if it is on guard. OutLeash: how far from it the guard goes for foes. */
	AActor* GuardWardOf(const AVLKing* Unit, float* OutLeash = nullptr) const;
	void GetGuards(const AActor* Ward, TArray<AVLKing*>& Out) const;
	bool IsRoaming(const AVLKing* Unit) const;
	/** The route it walks with its group, if any: its points, whether it loops (a patrol), the one it heads for. */
	bool GetRoute(const AVLKing* Unit, TArray<FVector>& OutPoints, bool& bOutLoop, int32& OutNext, int32* OutId = nullptr) const;
	/** "Patrolling", "Guarding the Castle", "Holding", "Roaming", "Attack-move", or empty: for the selection panel. */
	FString DescribeOrders(const TArray<AVLKing*>& Units) const;
	// march together: on the march everyone keeps the slowest one's pace (always in a formation; Loose: the setting)
	bool MarchTogether(const TArray<AVLKing*>& Units, EVLFormation Shape) const;
	bool SelectionMarchTogether() const;
	/** M: the setting of the selected platoon (else of loose selections), on / off; a march under way follows. */
	void ToggleMarchTogether();
	/**
	 * The pace of every march under way, in one place: a group order that marches together (OrderMove, and so the
	 * legs of a patrol or an attack-move, a Shift pathway, followers sent after their leader) gives its units one
	 * AVLKing::MarchId. Each unit on a march walks no faster than the slowest of those marching with it: its march's,
	 * and, a platoon member, the platoon's members on a march (walking or running, each at the speed it was sent at).
	 * And the march closes up as it goes: those ahead of the body along the way slow down, those behind hurry (up to
	 * their run), since troops of one pace never close a gap by themselves (the constants below).
	 * A unit in a fight or a chase, played by hand, or no longer on an order is at its own pace and counts for
	 * nobody's. Called when an order is given, when a platoon's members change or one falls, and four times a
	 * second (TickOrders) so a march follows whoever drops out of it or joins it.
	 */
	void UpdateMarchPace();
	// A march closes up along its way (UpdateMarchPace; cm of the way left to walk):
	static constexpr float MarchSlack = 250.f;         // this far ahead of / behind the body nothing changes
	static constexpr float MarchSlowest = 0.4f;        // the slowest those ahead go, as a share of the march's pace
	static constexpr float MarchStraggler = 6000.f;    // one further behind the body's middle than this is not waited for
	static constexpr float MarchSettle = 900.f;        // the last of the way: each to its own place, at the march's pace
	// the player's armed clicks
	void Arm(EVLArm Mode);
	EVLArm GetArmed() const;
	/** A: attack-move. (Attack-ground is no longer the player's: no key and no button; OrderAttackGround and
	 *  vl.ArmGround are kept for tests.) */
	void CycleAttackArm();
	/** K: the first press asks (an alert), a second within DismissAskSeconds dismisses the selection's troops. */
	void DismissCommand();
	bool IsDismissAsked() const;
	static constexpr float DismissAskSeconds = 2.5f;
	static constexpr float ArmSeconds = 10.f;
	/** Does the selection have anyone who can guard (V)? */
	bool SelectionCanGuard() const;

	// ---- platoons (1..6)
	static constexpr int32 MaxPlatoons = 6;
	void AssignPlatoon(int32 Index, const TArray<AVLKing*>& Units);
	void AddToPlatoon(int32 Index, const TArray<AVLKing*>& Units);
	void GetPlatoon(int32 Index, TArray<AVLKing*>& Out) const;
	EVLFormation PlatoonFormation(int32 Index) const { return Platoons[FMath::Clamp(Index, 0, MaxPlatoons - 1)].Formation; }
	EVLStance PlatoonStance(int32 Index) const { return Platoons[FMath::Clamp(Index, 0, MaxPlatoons - 1)].Stance; }
	/** The platoon panel's buttons: the next formation / stance of platoon Index (the stance pushed to its members),
	 *  and breaking it up (Delete; its troops stay where they are). */
	void CyclePlatoonFormation(int32 Index);
	void CyclePlatoonStance(int32 Index);
	void DisbandPlatoon(int32 Index);
	/** G: the selection's stance, Aggressive > Defensive > Hold (its platoon's, pushed to the members; else each unit's). */
	void CycleStance();
	/** The selection's stance (its platoon's, or its first unit's). */
	EVLStance SelectionStance() const;
	static const TCHAR* StanceName(EVLStance Stance);
	/** The platoon these units are exactly the members of, or INDEX_NONE. */
	int32 PlatoonOf(const TArray<AVLKing*>& Units) const;
	/** The platoon a unit is in (the first, if several), or INDEX_NONE; every living member's at once (the HUD, once
	 *  a frame); the selection as a set (IsSelected for many units). */
	int32 PlatoonIndexOf(const AVLKing* Unit) const;
	void GetPlatoonMap(TMap<const AVLKing*, int32>& Out) const;
	void GetSelectionSet(TSet<const AVLKing*>& Out) const;
	/** "Swordsmen", "Archers", "Mixed host", ... from who is in it. */
	FString PlatoonName(int32 Index) const;
	FVector PlatoonCentre(int32 Index) const;
	/**
	 * Platoon leaders. A platoon gets one when it is formed (Ctrl + N, the starting army, the first recruit into an
	 * empty one): King David if he is in it, else its longest-serving troop that is not a Builder; a leader re-formed
	 * into the same platoon keeps the post. If the leader falls (or leaves the platoon, or it is disbanded) the
	 * platoon has none: there is no succession, and it carries on as a plain group. A member becomes leader when the
	 * player takes control of it (MakeLeader) or when platoon members are ordered to follow it (OrderFollow). A
	 * leader takes the front-middle slot of its formation on a move, so the platoon forms up on it.
	 */
	AVLKing* GetPlatoonLeader(int32 Index) const;
	bool IsPlatoonLeader(const AVLKing* Unit) const;
	/** Unit becomes its platoon's leader (false: it is in none). bRally: the platoon's idle members fall in behind
	 *  it (OrderFollow) as well. */
	bool MakeLeader(AVLKing* Unit, bool bRally = false);
	/**
	 * The recruits' platoon (the platoon panel's flag, the main game's "recruits join here"): new swordsmen and
	 * archers from every barracks and range join it and march to it (UVLBattle::SpawnRecruit), unless the building
	 * has its own Joins platoon. One at a time; cleared by clicking the flag again, by disbanding the platoon or when
	 * its last troop falls. A platoon of RallyPlatoonCap or more takes no more: they wait in the yard as before.
	 */
	void SetRallyPlatoon(int32 Index);
	/** The flagged platoon, or INDEX_NONE (none, or it has nobody left). */
	int32 GetRallyPlatoon() const;
	/** The flagged platoon if it can take one more recruit, else INDEX_NONE. */
	int32 RallyPlatoonFor() const;
	static constexpr int32 RallyPlatoonCap = 24;

	// ---- the watch tower
	/** Does this building have a lookout archers can man (tag Lookout:..., from SM_WatchTower.json)? */
	static bool IsTower(const AActor* Building);
	/** The archers among Units walk to the tower's door and appear on its lookout; the others go and stand by the door. */
	void OrderGarrison(const TArray<AVLKing*>& Units, AActor* Tower, bool bRun);
	/** Everyone on the lookout comes down and forms up in front of the door (the tower's own archers stay up). */
	void EmptyTower(AActor* Tower);
	/** Puts a unit straight on a free post of the tower's lookout (the tower's own archers, UVLBattle). False if none
	 *  is free. */
	bool PutOnLookout(AVLKing* Unit, AActor* Tower);
	int32 FreePosts(const AActor* Tower) const;
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
	/** An order's marker there (one given outside the calls here: a Builder's queued walk). */
	void ShowMarker(const FVector& At) { AddMarker(At); }
	static constexpr float MarkerSeconds = 0.7f;

private:
	struct FPlatoon
	{
		TArray<TWeakObjectPtr<AVLKing>> Members;
		EVLFormation Formation = EVLFormation::Line;
		EVLStance Stance = EVLStance::Aggressive;
		bool bMarchTogether = true;
		TWeakObjectPtr<AVLKing> Leader;     // (none: no leader; see GetPlatoonLeader)
	};
	/** One unit keeping with the one it follows (OrderFollow). */
	struct FFollower
	{
		TWeakObjectPtr<AVLKing> Unit;
		TWeakObjectPtr<AVLKing> Leader;
		FVector2D SentFor = FVector2D(1e9f, 1e9f);  // where the leader was when it was last sent after it
		double SentAt = -100.0;
	};
	TArray<FFollower> Followers;
	void TickFollowers();
	/** The most senior of Units to lead them (see GetPlatoonLeader), or null. */
	static AVLKing* PickLeader(const TArray<AVLKing*>& Units);
	/** A group's way through points: a patrol (loops) or an attack-move (stops at the last). */
	struct FRoute
	{
		TArray<TWeakObjectPtr<AVLKing>> Members;
		TArray<FVector> Points;
		int32 Next = 0;
		bool bLoop = true;
		bool bRun = false;
		EVLFormation Shape = EVLFormation::Line;
		float Settle = 0.f;         // seconds before it next looks whether the leg is done
		int32 Tries = 0;            // legs walked again after a fight (or a block) that left them short of the point
		int32 Id = 0;
	};
	struct FGuardPost
	{
		TWeakObjectPtr<AVLKing> Unit;
		TWeakObjectPtr<AActor> Ward;
		FVector2D Offset = FVector2D::ZeroVector;   // from the ward's middle (a unit) / the post itself (a building)
		FVector2D SentFor = FVector2D(1e9f, 1e9f);  // where the ward was when it was last sent to its post
		bool bSent = false;
		int32 Platoon = INDEX_NONE;                 // a platoon's guard: the ward is one of its members (see OrderGuard)
	};
	struct FRoamer
	{
		TWeakObjectPtr<AVLKing> Unit;
		TArray<FVector2D> Visited;
		float LegTime = 0.f;
	};
	void IssueLeg(FRoute& R);
	struct FChain
	{
		TArray<TWeakObjectPtr<AVLKing>> Members;
		TArray<FChainItem> Items;           // [0] is under way once bStarted
		bool bStarted = false;
		EVLFormation Shape = EVLFormation::Line;
		TWeakObjectPtr<AVLKing> Rejoin;
		float Settle = 0.f;                 // seconds before it next looks whether the item is done
		int32 Id = 0;
	};
	TArray<FChain> Chains;
	int32 NextChainId = 1;
	void IssueChainItem(FChain& C);
	void TickChains(float Dt);
	int32 FindRoute(const TArray<AVLKing*>& Units, bool bLoop) const;
	bool WardPos(const AActor* Ward, FVector& Out) const;
	bool PickRoamPoint(FRoamer& R);
	void GuardPostWorld(const FGuardPost& G, FVector2D& Out) const;
	TArray<FRoute> Routes;
	TArray<FGuardPost> GuardPosts;
	TArray<FRoamer> Roamers;
	int32 NextRouteId = 1;
	float OrdersClock = 0.f;
	bool bQuietMove = false;        // a leg of a standing order: no order marker
	bool bLooseMarchTogether = true;
	/** Units given a march (MarchId) that UpdateMarchPace looks after; let go of once off it. */
	TArray<TWeakObjectPtr<AVLKing>> Marchers;
	int32 NextMarchId = 1;
	/** A unit taken out of its platoon (or the platoon broken up): its own pace again, off the march. */
	void LeftPlatoon(AVLKing* Unit);
	EVLArm Armed = EVLArm::None;
	double ArmedAt = -1.0;
	double DismissAskedAt = -100.0;
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
	int32 RallyPlatoon = INDEX_NONE;
	EVLFormation LooseFormation = EVLFormation::Line;
	TArray<FTower> Towers;
	TArray<FMarker> Markers;
};

namespace VLFormation
{
	/** The main game's SRFormation::ComputeSlots: a destination slot for every unit, in the same order as Units.
	 *  Leader (one of Units, or null): it takes the front-middle slot of its ranks (melee or archers), the formation's
	 *  anchor (not for Loose). */
	void ComputeSlots(const TArray<AVLKing*>& Units, const FVector2D& Destination, TArray<FVector2D>& OutSlots, EVLFormation Shape, const AVLKing* Leader = nullptr);
}
