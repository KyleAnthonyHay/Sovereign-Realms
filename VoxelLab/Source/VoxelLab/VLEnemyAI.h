#pragma once

#include "CoreMinimal.h"
#include "VLAIWorld.h"

class UVLBattle;
class AVLKing;
class AActor;
enum class EVLBuilding : uint8;
enum class EVLFormation : uint8;
enum class EVLStance : uint8;

/** vl.AIDebug: 0 quiet, 1 the reasoning logged, 2 also drawn. */
int32 VLAIDebugLevel();

/**
 * How hard the commander plays at one difficulty (the main game's FSRAIProfile, USRAISubsystem::Profile, and the
 * squad and strategy knobs of this game's commander). It never gets extra resources: Easy gets less of its farms' and
 * mines' output. The table of every knob per difficulty is in the README (The battle > The enemy commander).
 */
struct FVLAIProfile
{
	// ---- the main game's (timing, odds, attack sizes, raids, economy)
	float FirstAttack = 240.f;     // earliest main attack (s)
	float Advantage = 1.5f;        // strength it wants over the expected defence before attacking
	float Regroup = 90.f;          // pause after an attack ends (s)
	int32 AttackCap = 8;           // most troops in the first attack, growing by AttackCapGrowth per attack, up to AttackCapMax
	int32 AttackCapGrowth = 3;
	int32 AttackCapMax = 24;
	bool bRaids = true;
	float FirstRaid = 360.f;
	float RaidInterval = 120.f;
	float AdaptWeight = 0.6f;      // how fully it answers the player's army mix (0 = never)
	float IncomeScale = 0.9f;      // share of its farms' and mines' output it gets
	int32 RecruitQueue = 2;        // recruits it keeps queued per barracks / range
	float Think = 1.f;             // seconds between decisions (economy, squads' orders)
	float RetreatHold = 0.7f;      // falls back when its local strength drops below this x the foe's
	bool bReinforce = true;
	bool bImpatient = true;        // attacks at near-even odds after waiting long
	int32 TowerArchers = 2;        // archers it puts on each of its watch towers' lookouts
	bool bUpgrades = true;         // raises mines and the barracks / range when gold piles up
	int32 Builders = 2;            // Builders it keeps (the main game's: Easy 1, else 2)
	float BuildCadence = 4.f;      // seconds after laying a site before it lays the next (Easy 8, Hard 2)
	// ---- strategy
	float StrategyEvery = 3.5f;    // seconds between two looks at its posture
	float ReactionDelay = 2.f;     // foes at home this long before the whole army turns to defend
	float Commitment = 0.12f;      // bonus the present posture keeps (no flip-flopping)
	float ContestWeight = 1.f;     // how much holding the middle / the Crown / a neutral mine appeals
	float ExpandWeight = 1.f;
	// ---- squads
	int32 PatrolMax = 3;           // troops on the home patrol (base perimeter and mine roads)
	float PatrolShare = 0.2f;
	float PatrolRadius = 11000.f;  // its buildings this near the castle are on the patrol's loop
	int32 GuardMax = 3;            // troops posted round the castle (and its Builders, its far mine)
	float GuardShare = 0.12f;
	int32 BuilderGuards = 1;       // guards sent with a Builder working far from the castle
	int32 PicketFrom = 10;         // a field army this large at home sends a picket (a third, 3 to 8) to hold a second point
	int32 MaxRaids = 1;            // raid parties out at once
	int32 RaidSize = 3;
	bool bFlank = false;           // a second body round by a flank bridge when it attacks (maps that have them)
	float InterceptOdds = 1.6f;    // goes for a foe body caught in the open with this x its strength (0 = never)
	float InterceptRange = 6000.f; // ... this far from where its field army stands
	// ---- micro
	float MicroEvery = 1.f;        // seconds between two looks at its fights (0 = none)
	int32 FocusFire = 1;           // 0 none, 1 its archers pick the weakest / most valuable foe, 2 its swordsmen too
	bool bKite = true;             // archers step back behind the swords from a swordsman at their throat
	float PullBack = 0.25f;        // a troop below this share of its health leaves the fight for the castle (0 = never)
	bool bAvoidTowers = true;      // keeps its holding points and raids out of the foe's tower reach
	float PushAfter = 1500.f;      // the clock (s) from which, about even or ahead, it goes for the castle (FinalPush)

	static FVLAIProfile For(int32 Difficulty);
};

/** A foe the commander has seen: where, what, how hurt, and when. */
struct FVLSighting
{
	TWeakObjectPtr<AVLKing> Unit;
	FVector2D Pos = FVector2D::ZeroVector;
	bool bRanged = false;
	bool bKing = false;
	float HealthFrac = 1.f;
	float Time = 0.f;
};

/** Foes seen together lately: a body of the foe's army. */
struct FVLFoeGroup
{
	FVector Centre = FVector::ZeroVector;
	float Power = 0.f;
	int32 Count = 0;
	bool bExposed = false;          // out in the open: far from the foe's castle and outside its towers' reach
	bool bAtOurHome = false;
};

/** What the army as a whole is doing (re-weighed every StrategyEvery). */
enum class EVLPosture : uint8
{
	Expand,     // claim veins, build farms and mines; the field army holds the home side's crossing
	Defend,     // foes at home: everyone goes to meet them
	Contest,    // hold the middle (the Crown, the crossing, a neutral mine) with the field army
	Harass,     // raid the foe's outlying farms and mines with small fast parties; the field army screens
	Attack,     // the field army goes for the foe's buildings
	Regroup,    // after losses: back under its towers, rebuild
	Num
};

enum class EVLSquadRole : uint8
{
	Patrol,     // the home patrol: the base's perimeter and its mine roads
	Guard,      // posted round the castle, Builders working far out, a far mine (Hard)
	Field,      // the field army
	Reserve,    // recruits gathering while the field army is away (they reinforce it)
	Raid,       // a raid party
	Flank,      // a field army's second body, round by a flank bridge (Hard)
	Picket      // a large field army's detachment holding a second point: a flank bridge's near end, an outlying mine
};

enum class EVLSquadTask : uint8
{
	Idle,
	Patrol,     // OrderPatrol round the base
	Guard,      // OrderGuard on its wards
	Hold,       // at a holding point, in formation, defensive stance
	Attack,     // attack-move at a foe building, then knock it down
	Raid,
	Defend,     // attack-move at foes at home
	Intercept,  // attack-move at a foe body caught in the open
	Retreat     // a plain move home at a run (no stopping to fight)
};

/** A body of troops with one role and one task. */
struct FVLSquad
{
	int32 Id = 0;
	EVLSquadRole Role = EVLSquadRole::Field;
	EVLSquadTask Task = EVLSquadTask::Idle;
	TArray<TWeakObjectPtr<AVLKing>> Units;
	TWeakObjectPtr<AActor> Target;      // what it attacks or raids
	FVector Goal = FVector::ZeroVector; // where it goes / holds
	FString GoalName;
	int32 StartSize = 0;
	float StartPower = 0.f;
	float TaskSince = 0.f;
	float LastFight = 0.f;
	float LastOrder = -100.f;
	float Reorder = 0.f;
	float Departs = 0.f;                // a field army waiting for its flank to get ahead
	uint32 OrderedFor = 0;              // the members its present order was given to (a new member: give it again)
	FVector OrderedGoal = FVector(1e9f);
	TArray<FVector> Via;                // a route's points before the goal (a flank bridge)
	float TargetHealth = -1.f;          // the target's health when it last fell (an attack that does no harm for long ends)
	float ProgressAt = 0.f;
	float ProgressDealt = -1.f;         // its side's damage to the foe's buildings and kills when it last made headway

	void Prune();
	int32 Num() const { return Units.Num(); }
	bool Has(const AVLKing* U) const;
	void Gather(TArray<AVLKing*>& Out, FVector& Centre) const;
	uint32 MemberHash() const;
	bool IsOut() const { return Task == EVLSquadTask::Attack || Task == EVLSquadTask::Raid; }
};

/**
 * One kingdom's commander: the main game's FSRCommander and USRAISubsystem grown into a commander of three layers, on
 * this game's units, buildings and orders (UVLCommand's standing orders). It plays by the player's rules and knows only
 * what it has seen (the player's troops within SightRadius of its own troops and buildings, its Spy's 33.8 m, a Spy
 * only at 45% of that; remembered for MemoryTime; buildings are known).
 *
 *  1. PERCEPTION (VLAIWorld.*, Observe, TrackEvents): what it has seen of the foe's army and where its bodies are
 *     (FoeGroups: exposed or at its door), an influence map of both sides' strength, the map's strategic points, and
 *     what happened lately (its buildings struck or lost, raids, troops lost).
 *  2. STRATEGY (ChooseStrategy, every StrategyEvery): a posture chosen by utility: Expand, Defend, Contest, Harass,
 *     Attack, Regroup, weighed from the army ratio (its strength over the foe's estimate), the economy (mines, free
 *     veins), the clock (FirstAttack), the danger at home (held ReactionDelay before it turns everyone round), recent
 *     losses and the difficulty; the present posture keeps a Commitment bonus.
 *  3. SQUADS (VLAISquads.cpp): the army is split into squads with roles: the home Patrol (OrderPatrol round its
 *     buildings and mine roads), the Guard (OrderGuard on the castle, a Builder working far out, a far mine), the
 *     Field army (holds the posture's point in a Line, defensive stance: its side of the crossing, the Crown, a
 *     neutral mine, its tower's cover; attacks; defends; intercepts a foe body caught in the open; retreats), a Reserve
 *     that reinforces an attack, Raid parties (Harass) and a Flank body round by a side bridge (Hard). Squads advance
 *     with OrderAttackMove; MICRO every MicroEvery: focus fire on the weakest / most valuable foe in reach, archers
 *     stepping back behind the swords, badly hurt troops sent home to guard the castle, a tower in the way taken down
 *     only with enough strength (else the target is dropped).
 *  4. ECONOMY (ManageBuilding, Recruit, ManageUpgrades, ManageTowers, ManageSpy): the main game's build order and wants
 *     with Builders, driven by the strategy: more barracks / ranges when the army ratio is bad, a tower by what was
 *     raided, mines on the safest free veins (the Crown's while it holds it), no site where the foe is stronger.
 *  DEBUG: vl.AIDebug 1 logs the posture (with every utility), the squads and their tasks each strategy look; 2 also
 *  draws them, the strategic points and the influence map; vl.AI [team] logs a full report with the influence map as
 *  text; vl.AIvsAI 1 [difficulty] gives the player's side a commander too.
 */
struct FVLCommander
{
	int32 Team = 1;
	int32 Difficulty = 1;
	bool bActive = false;
	FVLAIProfile Prof;
	float Clock = 0.f;
	float ThinkClock = 0.f;
	float StrategyClock = 0.f;
	float MicroClock = 0.f;

	// ---- perception
	TArray<FVLSighting> Seen;
	TArray<FVLFoeGroup> FoeGroups;
	float FoeArmyEstimate = 0.f;
	float FoeArcherShare = 0.4f;
	int32 FoeAttacks = 0;
	float LastFoeAttack = -1000.f;
	bool bFoeAtHome = false;
	float HomeThreat = 0.f;             // foes' strength at its buildings now
	FVector HomeThreatAt = FVector::ZeroVector;
	float ThreatSince = -1.f;           // foes at home since (Clock), or < 0
	FVLAIMap Map;
	FVLInfluence Influence;
	TArray<FVLAIEvent> Events;
	TMap<TWeakObjectPtr<AActor>, double> KnownHits;     // its buildings' last hit (world time) it has noted
	TSet<TWeakObjectPtr<AActor>> KnownLost;
	TMap<TWeakObjectPtr<AVLKing>, FVector4f> Roll;      // its troops last think (position, power)
	float LastRaided = -1000.f;
	FVector RaidedAt = FVector::ZeroVector;
	float ArmyPower = 0.f;

	// ---- strategy
	EVLPosture Posture = EVLPosture::Expand;
	float PostureSince = 0.f;
	float Utility[int32(EVLPosture::Num)] = {};
	float ArmyRatio = 1.f;
	FString PostureWhy;
	int32 ContestPoint = INDEX_NONE;    // the point of Map the field army holds in Contest
	int32 SafeVeins = 0;                // free veins within reach where the foe is not the stronger

	// ---- squads
	TArray<FVLSquad> Squads;
	int32 NextSquadId = 1;
	TMap<TWeakObjectPtr<AVLKing>, float> Kited;     // archers' last step back (Clock)
	TMap<TWeakObjectPtr<AVLKing>, float> Retargeted;    // troops' last change of foe on its order (Clock)
	TMap<TWeakObjectPtr<AVLKing>, FVector4f> Moved;     // where a troop out on an attack last made way (position, Clock)
	TMap<TWeakObjectPtr<AVLKing>, FVector> Stuck;       // troops on ground they cannot leave (left out of the squads while there)
	int32 Stat[4] = { 0, 0, 0, 0 };     // focus-fire orders, steps back, troops pulled back, interceptions (the report)
	float NextWaveTime = 0.f;
	float NextRaidTime = 0.f;
	int32 WavesSent = 0;
	int32 RaidsSent = 0;
	float LastReinforce = -100.f;

	// ---- economy
	float ShieldRatio = 0.55f;
	float NextSpyOrder = 0.f;           // when its Spy is next sent somewhere to look
	float NextBuildTry = 2.f;           // when it next looks at what to build
	float NextGarrison = 0.f;
	int32 BuildStep = 0;                // how far through its build order it is
	TMap<int32, float> BuildBlocked;    // a kind of building that found no room: not tried again until then

	static constexpr float SightRadius = 2600.f;
	static constexpr float MemoryTime = 90.f;
	static constexpr float DefendRadius = 3200.f;
	static constexpr float RetreatFraction = 0.3f;
	static constexpr float BaseShieldRatio = 0.55f;
	static constexpr int32 MinAttackSize = 4;
	static constexpr int32 WaveSizeMax = 30;

	void Reset(UVLBattle* Battle, int32 InTeam, int32 Difficulty);
	void Step(UVLBattle* Battle, float Dt);
	/** Seconds until its next main attack may leave (negative once it is due). */
	float NextWaveIn() const { return NextWaveTime - Clock; }
	/** While an attack is out its next one has no time yet: NextWaveTime is Clock + WaveHeld until the attack ends. */
	static constexpr float WaveHeld = 1e6f;
	/** The longest it ever waits for its next attack with none out (s): the longer of its first attack's time and its
	 *  pause between two. Step holds NextWaveTime to that, whatever left it further off. */
	float MaxWaveWait() const { return FMath::Max(Prof.FirstAttack, Prof.Regroup); }
	bool IsAttacking() const;
	/** How many troops its next main attack wants (balance runs, 2026-11-22): its attack cap for this wave (AttackCap,
	 *  + AttackCapGrowth a wave sent), at most 60% of what it can house. Below that it waits, unless its housing is full
	 *  or the odds are overwhelming (twice what it wants): attacks of four or five into a defended base bled both
	 *  armies and no match ever ended. */
	int32 AttackWant(const UVLBattle* B) const;
	/** The final push (balance runs, 2026-11-22: no match between two commanders ever ended, not in 90 minutes): from
	 *  PushAfter of the clock on, with an army about the foe's (ArmyRatio 0.9 or more), its attacks go for the foe's
	 *  castle and do not fall back until they are down to two fifths. */
	bool FinalPush() const;
	/** Its field army is out on the final push, at the foe's castle. */
	bool IsPushing(const UVLBattle* B) const;
	FString Describe() const;
	/** The full picture for the log (vl.AI): posture and utilities, squads and their members, the map's points, recent
	 *  events, the influence map (bMap). */
	void LogReport(UVLBattle* B, bool bMap) const;
	static const TCHAR* PostureName(EVLPosture P);
	static const TCHAR* RoleName(EVLSquadRole R);
	static const TCHAR* TaskName(EVLSquadTask T);

	/** Fighting strength of a troop: sqrt(health x damage per second), archers x1.5 for their reach; a swordsman = 1. */
	static float UnitPower(const AVLKing* Unit);
	static float KindPower(bool bRanged, float HealthFrac = 1.f);
	static float BuildingPower(UVLBattle* Battle, const AActor* Building);

private:
	void Think(UVLBattle* B);
	// perception
	void Observe(UVLBattle* B);
	void TrackEvents(UVLBattle* B, const TArray<AVLKing*>& Army);
	void UpdateInfluence(UVLBattle* B, const TArray<AVLKing*>& Army);
	void AddEvent(EVLAIEvent Kind, const FVector& At, float Power, const FString& What, AActor* Actor = nullptr);
	float RecentLoss(float Window) const;
	int32 CountEvents(EVLAIEvent Kind, float Window) const;
	// strategy
	void ChooseStrategy(UVLBattle* B);
	// economy
	void Adapt(UVLBattle* B);
	void Recruit(UVLBattle* B, const TArray<AVLKing*>& Mine);
	/** Its Spy (Normal, Hard): trained when the rules allow once the army has a core of six, kept out of the squads,
	 *  and sent from one look-out to the next beside the foe's buildings (its castle most often), far enough out not
	 *  to be noticed; hurt, it goes home and stays (the main game's ManageScout). */
	void ManageSpy(UVLBattle* B, const TArray<AVLKing*>& Mine);
	void ManageUpgrades(UVLBattle* B);
	/** What to build next and where (the main game's ManageEconomy, driven by the posture): one site at a time per Builder. */
	void ManageBuilding(UVLBattle* B, const TArray<AVLKing*>& Mine);
	/** Lays a site of Kind (the main game's TryBuild): trainers beside the castle toward the foe, farms behind it, towers
	 *  out toward the foe and apart (or by Near when given: a raided farm or mine), a mine on the best free vein. */
	bool TryBuild(UVLBattle* B, EVLBuilding Kind, const FVector* Near = nullptr);
	void ManageTowers(UVLBattle* B, TArray<AVLKing*>& Pool);
	// squads (VLAISquads.cpp)
	void ManageSquads(UVLBattle* B, TArray<AVLKing*>& Pool);
	void RunSquads(UVLBattle* B);
	void Micro(UVLBattle* B);
	FVLSquad& SquadFor(EVLSquadRole Role);
	FVLSquad* FindSquad(EVLSquadRole Role);
	void SetTask(FVLSquad& S, EVLSquadTask Task, const FString& Why);
	void RunPatrol(UVLBattle* B, FVLSquad& S);
	void RunGuard(UVLBattle* B, FVLSquad& S);
	void RunField(UVLBattle* B, FVLSquad& S);
	void RunReserve(UVLBattle* B, FVLSquad& S);
	void RunPicket(UVLBattle* B, FVLSquad& S);
	/** The second point a picket holds (not where the field army holds), or false. */
	bool PicketPoint(UVLBattle* B, FVector& OutAt, FString& OutName) const;
	void HoldAt(UVLBattle* B, FVLSquad& S, const FVector& Where, const FString& Name);
	void MarchTo(UVLBattle* B, FVLSquad& S, const FVector& Where, bool bRun, EVLFormation Shape, bool bFight = true);
	bool LaunchAttack(UVLBattle* B, FVLSquad& Field);
	/** The body an attack would take (the field army's and its picket's troops not fighting, the healthiest, up to the
	 *  attack cap) and the target it would go for (the foe on the way counted), with the defence it expects. The
	 *  strategy and the launch use the same, so that the posture and the deed agree. */
	AActor* PlanAttack(UVLBattle* B, TArray<AVLKing*>& OutBody, FVector& OutFrom, float& OutPower, float& OutDefence);
	bool LaunchRaid(UVLBattle* B);
	/** One look at a body that is out (an attack or a raid); false once it has ended (its troops sent home). */
	bool StepAttack(UVLBattle* B, FVLSquad& S);
	void EndAttack(UVLBattle* B, FVLSquad& S, const FString& Why);
	void MergeInto(FVLSquad& From, FVLSquad& To);
	void FocusFire(UVLBattle* B, FVLSquad& S, const TArray<AVLKing*>& W);
	void Kite(UVLBattle* B, FVLSquad& S, const TArray<AVLKing*>& W);
	void PullBack(UVLBattle* B, FVLSquad& S, const TArray<AVLKing*>& W);
	// places
	FVector MusterPoint(UVLBattle* B) const;
	FVector2D TowardFoe(UVLBattle* B) const;
	/** Where the field army waits on its own side: its end of the crossing / the Crown's bridge, under its tower. */
	FVector ForwardPoint(UVLBattle* B, FString* OutName = nullptr) const;
	/** Its safest gathering point: in front of the castle, under the nearest tower toward the foe. */
	FVector SafePoint(UVLBattle* B) const;
	/** The point to contest (the best of the map's by worth and reach), or INDEX_NONE. Its holding spot in OutAt. */
	int32 PickContest(UVLBattle* B, float FieldPower, FVector* OutAt, float* OutScore) const;
	/** P moved back toward its castle until it is out of the foe's towers' and castle's reach (bAvoidTowers). */
	FVector OutOfReach(UVLBattle* B, const FVector& P) const;
	bool InFoeReach(UVLBattle* B, const FVector& P, float Margin, const AActor** OutBy = nullptr) const;
	/** Where a body attacking a building goes: in front of its door (always on ground it can walk to; the near side of a
	 *  mine in a cliff may not be). */
	FVector AttackSpot(UVLBattle* B, const AActor* Target) const;
	void PatrolPoints(UVLBattle* B, TArray<FVector>& Out) const;
	// strength
	float ExpectedDefence(UVLBattle* B, const FVector& At, bool bSeenOnly) const;
	float LocalFoePower(UVLBattle* B, const FVector& At, float Radius) const;
	AActor* PickTarget(UVLBattle* B, const FVector& From, float Power, bool bRaid, float* OutDefence, const TArray<const AActor*>* Skip = nullptr) const;
	/** The foe's strength on the way from From to the target (the influence map's peak along the route): a mine behind
	 *  the foe's castle is only as weakly held as the castle it is behind. */
	float RouteDefence(UVLBattle* B, const FVector& From, const FVector& To) const;
	static float SumPower(const TArray<AVLKing*>& Units);
	int32 Foe() const { return 1 - Team; }
	void DebugDraw(UVLBattle* B) const;
};
