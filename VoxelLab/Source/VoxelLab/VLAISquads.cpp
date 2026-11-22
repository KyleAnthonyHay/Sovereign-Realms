#include "VLEnemyAI.h"
#include "VoxelLab.h"
#include "VLBattle.h"
#include "VLKing.h"
#include "VLCommand.h"
#include "VLConstruction.h"
#include "VLArcherCombat.h"
#include "Engine/World.h"

// The commander's third layer (VLEnemyAI.h, class comment): its squads, their tasks and their tactics. Orders go
// through UVLCommand's standing orders (OrderPatrol, OrderGuard, OrderAttackMove) and the plain ones (OrderMove,
// OrderAttack, OrderGarrison); a tactical change of foe or step back is given as the unit's own doing (bInnerOrder),
// so the squad's patrol, guard or route goes on.


namespace
{
	FString Clk(float T)
	{
		return FString::Printf(TEXT("%d:%02d"), int32(T) / 60, int32(T) % 60);
	}

	void SetStance(const TArray<AVLKing*>& W, EVLStance Stance)
	{
		for (AVLKing* U : W)
		{
			if (U->Stance != Stance)
			{
				U->Stance = Stance;
				U->Post = U->GetFeet();
			}
		}
	}

	bool AnyEngaged(const TArray<AVLKing*>& W)
	{
		for (AVLKing* U : W)
		{
			if (VLAI::Engaged(U))
			{
				return true;
			}
		}
		return false;
	}

	/** How much a foe is worth killing first: hurt, an archer (fragile, hurts), a Spy, King David only when nearly down. */
	float FoeValue(const AVLKing* F)
	{
		float V = (1.f - F->GetHealthFrac()) * 1.5f;
		if (F->IsRanged()) { V += 0.6f; }
		if (F->KindId() == EVLUnitKind::Spy) { V += 0.5f; }
		if (!F->IsTroop()) { V += F->GetHealthFrac() < 0.3f ? 0.6f : -0.6f; }       // (he rises again at his castle)
		return V;
	}
}

// ------------------------------------------------------------------------------------------------ the squad

void FVLSquad::Prune()
{
	Units.RemoveAll([](const TWeakObjectPtr<AVLKing>& U) { return !U.IsValid() || U->IsDead(); });
}

bool FVLSquad::Has(const AVLKing* U) const
{
	return Units.ContainsByPredicate([U](const TWeakObjectPtr<AVLKing>& X) { return X.Get() == U; });
}

void FVLSquad::Gather(TArray<AVLKing*>& Out, FVector& Centre) const
{
	Out.Reset();
	Centre = FVector::ZeroVector;
	for (const TWeakObjectPtr<AVLKing>& U : Units)
	{
		if (U.IsValid() && U->IsAlive())
		{
			Out.Add(U.Get());
			Centre += U->GetFeet();
		}
	}
	if (Out.Num() > 0)
	{
		Centre /= Out.Num();
	}
}

uint32 FVLSquad::MemberHash() const
{
	uint32 H = uint32(Units.Num()) * 977u;
	for (const TWeakObjectPtr<AVLKing>& U : Units)
	{
		H += GetTypeHash(U.Get()) * 2654435761u;        // (order does not matter)
	}
	return H;
}

bool FVLCommander::IsAttacking() const
{
	for (const FVLSquad& S : Squads)
	{
		if (S.IsOut() && S.Num() > 0)
		{
			return true;
		}
	}
	return false;
}

FVLSquad* FVLCommander::FindSquad(EVLSquadRole Role)
{
	return Squads.FindByPredicate([Role](const FVLSquad& S) { return S.Role == Role; });
}

FVLSquad& FVLCommander::SquadFor(EVLSquadRole Role)
{
	if (FVLSquad* S = FindSquad(Role))
	{
		return *S;
	}
	FVLSquad& S = Squads.AddDefaulted_GetRef();
	S.Id = NextSquadId++;
	S.Role = Role;
	S.TaskSince = Clock;
	return S;
}

void FVLCommander::SetTask(FVLSquad& S, EVLSquadTask Task, const FString& Why)
{
	if (S.Task == Task && S.GoalName == Why)
	{
		return;
	}
	const bool bNewTask = S.Task != Task;
	S.Task = Task;
	S.GoalName = Why;
	S.TaskSince = Clock;
	S.OrderedFor = 0;
	S.OrderedGoal = FVector(1e9f);
	if (bNewTask || VLAIDebugLevel() >= 1)
	{
		UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] %s#%d (%d) -> %s %s"), Team, *Clk(Clock), RoleName(S.Role), S.Id, S.Num(), TaskName(Task), *Why);
	}
}

void FVLCommander::MergeInto(FVLSquad& From, FVLSquad& To)
{
	for (const TWeakObjectPtr<AVLKing>& U : From.Units)
	{
		if (U.IsValid() && !To.Has(U.Get()))
		{
			To.Units.Add(U);
		}
	}
	From.Units.Reset();
}

void FVLCommander::MarchTo(UVLBattle* B, FVLSquad& S, const FVector& Where, bool bRun, EVLFormation Shape, bool bFight)
{
	UVLCommand* Command = UVLCommand::Get(B);
	TArray<AVLKing*> W;
	FVector C;
	S.Gather(W, C);
	if (!Command || W.Num() == 0)
	{
		return;
	}
	if (!bFight)
	{
		for (AVLKing* U : W)
		{
			Command->StopAttack(U);
		}
		Command->OrderMove(W, Where, bRun, Shape);
	}
	else if (S.Via.Num() > 0)
	{
		// round by its way points (a flank bridge), fighting what it meets
		Command->OrderAttackMove(W, S.Via[0], bRun, Shape, false);
		for (int32 i = 1; i < S.Via.Num(); ++i)
		{
			Command->OrderAttackMove(W, S.Via[i], bRun, Shape, true);
		}
		Command->OrderAttackMove(W, Where, bRun, Shape, true);
	}
	else
	{
		Command->OrderAttackMove(W, Where, bRun, Shape, false);
	}
	S.OrderedFor = S.MemberHash();
	S.OrderedGoal = Where;
	S.LastOrder = Clock;
}

// ------------------------------------------------------------------------------------------------ who goes where

void FVLCommander::ManageSquads(UVLBattle* B, TArray<AVLKing*>& Pool)
{
	TSet<AVLKing*> InPool;
	InPool.Append(Pool);
	for (FVLSquad& S : Squads)
	{
		S.Prune();
		S.Units.RemoveAll([&InPool](const TWeakObjectPtr<AVLKing>& U) { return !InPool.Contains(U.Get()); });     // (gone up a tower)
	}
	TSet<AVLKing*> Taken;
	for (const FVLSquad& S : Squads)
	{
		for (const TWeakObjectPtr<AVLKing>& U : S.Units)
		{
			Taken.Add(U.Get());
		}
	}
	const int32 N = Pool.Num();
	const int32 PatrolWant = N >= (Difficulty <= 0 ? 3 : 4) ? FMath::Clamp(FMath::RoundToInt(N * Prof.PatrolShare), 2, Prof.PatrolMax) : 0;
	int32 GuardWant = (Prof.GuardMax > 0 && N >= 6) ? FMath::Clamp(FMath::RoundToInt(N * Prof.GuardShare), 1, Prof.GuardMax) : 0;
	// Builders working far out want guards of their own (Normal, Hard)
	if (Prof.BuilderGuards > 0 && N >= 4)
	{
		const AActor* Castle = B->GetCastle(Team);
		TArray<AVLKing*> Builders;
		if (UVLConstruction* C = UVLConstruction::Get(B))
		{
			C->GetBuilders(Team, Builders);
		}
		for (AVLKing* Bd : Builders)
		{
			const UVLBuilderWork* Work = UVLBuilderWork::For(Bd, false);
			const AActor* Job = Work ? Work->GetJob() : nullptr;
			if (Job && Castle && B->DistanceTo(Castle, Job->GetActorLocation()) > 3500.f)
			{
				GuardWant += Prof.BuilderGuards;
			}
		}
		GuardWant = FMath::Min(GuardWant, Prof.GuardMax + Prof.BuilderGuards * 2);
	}
	FVLSquad* Field = FindSquad(EVLSquadRole::Field);
	if (Field && Field->Num() == 0 && !Field->IsOut() && Field->Task != EVLSquadTask::Idle)
	{
		SetTask(*Field, EVLSquadTask::Idle, TEXT("none left"));       // (a field army wiped out: the next troops are the new one)
		Field->Target.Reset();
		Field->Departs = 0.f;
	}
	const bool bFieldAway = Field && (Field->Task == EVLSquadTask::Attack || Field->Task == EVLSquadTask::Intercept || Field->Task == EVLSquadTask::Retreat);
	// the new: the guard first, then the patrol, then the field army (its reserve while it is away)
	for (AVLKing* U : Pool)
	{
		if (Taken.Contains(U))
		{
			continue;
		}
		FVLSquad* Guard = FindSquad(EVLSquadRole::Guard);
		FVLSquad* Patrol = FindSquad(EVLSquadRole::Patrol);
		if ((Guard ? Guard->Num() : 0) < GuardWant)
		{
			SquadFor(EVLSquadRole::Guard).Units.Add(U);
		}
		else if ((Patrol ? Patrol->Num() : 0) < PatrolWant)
		{
			SquadFor(EVLSquadRole::Patrol).Units.Add(U);
		}
		else
		{
			SquadFor(bFieldAway ? EVLSquadRole::Reserve : EVLSquadRole::Field).Units.Add(U);
		}
		Taken.Add(U);
	}
	// the field army back home: its reserve joins it
	Field = FindSquad(EVLSquadRole::Field);
	FVLSquad* Reserve = FindSquad(EVLSquadRole::Reserve);
	if (Reserve && Field && !bFieldAway)
	{
		MergeInto(*Reserve, *Field);
	}
	else if (Reserve && !Field)
	{
		Reserve->Role = EVLSquadRole::Field;
	}
	// a large field army at home: a picket of a third holds a second point (a flank bridge's near end, an outlying
	// mine, a vein on its half); a small one takes it back
	Field = FindSquad(EVLSquadRole::Field);
	if (Field && !bFieldAway && Posture != EVLPosture::Defend && Posture != EVLPosture::Attack)
	{
		FVLSquad* Picket = FindSquad(EVLSquadRole::Picket);
		const int32 Have = Picket ? Picket->Num() : 0;
		const int32 Total = Field->Num() + Have;
		FVector At;
		FString Name;
		const int32 WantPicket = (Total >= Prof.PicketFrom && PicketPoint(B, At, Name)) ? FMath::Clamp(FMath::RoundToInt(Total * 0.3f), 3, 8) : 0;
		if (WantPicket > Have)
		{
			TArray<AVLKing*> W;
			FVector C;
			Field->Gather(W, C);
			W.RemoveAll([](AVLKing* U) { return VLAI::Engaged(U) || U->GetHealthFrac() < 0.6f; });
			// alternately a sword and a bow, the healthiest
			W.Sort([](const AVLKing& X, const AVLKing& Y) { return X.GetHealthFrac() > Y.GetHealthFrac(); });
			TArray<AVLKing*> Pick;
			for (int32 Pass = 0; Pass < 2 && Pick.Num() < WantPicket - Have; ++Pass)
			{
				bool bBow = (Pick.Num() % 2) == 1;
				for (AVLKing* U : W)
				{
					if (Pick.Num() >= WantPicket - Have)
					{
						break;
					}
					if (!Pick.Contains(U) && (Pass == 1 || U->IsRanged() == bBow))
					{
						Pick.Add(U);
						bBow = !bBow;
					}
				}
			}
			if (Pick.Num() >= FMath::Min(3, WantPicket - Have))
			{
				FVLSquad& P = SquadFor(EVLSquadRole::Picket);
				Field = FindSquad(EVLSquadRole::Field);
				for (AVLKing* U : Pick)
				{
					Field->Units.Remove(U);
					P.Units.Add(U);
				}
			}
		}
		else if (WantPicket == 0 && Picket && Have > 0)
		{
			TArray<AVLKing*> W;
			FVector C;
			Picket->Gather(W, C);
			if (!AnyEngaged(W))
			{
				MergeInto(*Picket, *Field);
			}
		}
	}
	else if (Field && Posture == EVLPosture::Attack && !bFieldAway)
	{
		// an attack is coming: the picket joins the body that goes
		if (FVLSquad* Picket = FindSquad(EVLSquadRole::Picket))
		{
			TArray<AVLKing*> W;
			FVector C;
			Picket->Gather(W, C);
			if (!AnyEngaged(W))
			{
				MergeInto(*Picket, *Field);
			}
		}
	}
	// too many on the patrol or the guard (the army grew, or the pulled-back have not all got hurt): the healthy extra
	// to the field army, while it is quiet
	if (Posture != EVLPosture::Defend)
	{
		for (EVLSquadRole Role : { EVLSquadRole::Patrol, EVLSquadRole::Guard })
		{
			FVLSquad* S = FindSquad(Role);
			const int32 Want = Role == EVLSquadRole::Patrol ? PatrolWant : GuardWant;
			if (!S || S->Num() <= Want + 1)
			{
				continue;
			}
			TArray<AVLKing*> W;
			FVector C;
			S->Gather(W, C);
			if (AnyEngaged(W))
			{
				continue;
			}
			W.Sort([](const AVLKing& X, const AVLKing& Y) { return X.GetHealthFrac() > Y.GetHealthFrac(); });
			FVLSquad& To = SquadFor(bFieldAway ? EVLSquadRole::Reserve : EVLSquadRole::Field);
			S = FindSquad(Role);    // (SquadFor may have moved the array)
			for (int32 i = 0; i < W.Num() && S->Num() > Want; ++i)
			{
				if (W[i]->GetHealthFrac() > FMath::Max(Prof.PullBack, 0.3f) + 0.15f)
				{
					S->Units.Remove(W[i]);
					To.Units.Add(W[i]);
				}
			}
		}
	}
}

void FVLCommander::RunSquads(UVLBattle* B)
{
	for (int32 i = 0; i < Squads.Num(); ++i)
	{
		if (Squads[i].Num() == 0 && !Squads[i].IsOut())
		{
			continue;
		}
		switch (Squads[i].Role)
		{
		case EVLSquadRole::Patrol: RunPatrol(B, Squads[i]); break;
		case EVLSquadRole::Guard: RunGuard(B, Squads[i]); break;
		case EVLSquadRole::Field: RunField(B, Squads[i]); break;
		case EVLSquadRole::Reserve: RunReserve(B, Squads[i]); break;
		case EVLSquadRole::Picket: RunPicket(B, Squads[i]); break;
		case EVLSquadRole::Raid:
		case EVLSquadRole::Flank:
		{
			FVLSquad& S = Squads[i];
			// foes at home and outmatched there: a raid comes back to fight
			if (S.Role == EVLSquadRole::Raid && S.IsOut() && Posture == EVLPosture::Defend)
			{
				EndAttack(B, S, TEXT("recalled to defend"));
				break;
			}
			if (S.IsOut())
			{
				StepAttack(B, S);
			}
			else
			{
				// home again (or near enough, or long enough): back into the field army
				TArray<AVLKing*> W;
				FVector C;
				S.Gather(W, C);
				bool bAllIdle = true;
				for (AVLKing* U : W)
				{
					bAllIdle &= VLAI::Idle(U);
				}
				if (W.Num() == 0 || FVector::Dist2D(C, S.Goal) < 2500.f || (bAllIdle && Clock - S.TaskSince > 6.f) || Clock - S.TaskSince > 60.f)
				{
					FVLSquad& To = SquadFor(FindSquad(EVLSquadRole::Field) && FindSquad(EVLSquadRole::Field)->IsOut() ? EVLSquadRole::Reserve : EVLSquadRole::Field);
					MergeInto(Squads[i], To);
				}
			}
			break;
		}
		}
	}
	// a raid or a flank whose troops have all gone home or fallen: struck off (the standing roles stay)
	Squads.RemoveAll([](const FVLSquad& S) { return S.Num() == 0 && (S.Role == EVLSquadRole::Raid || S.Role == EVLSquadRole::Flank || S.Role == EVLSquadRole::Reserve || S.Role == EVLSquadRole::Picket); });
	if (Prof.bRaids && (Posture == EVLPosture::Harass || Posture == EVLPosture::Contest || Posture == EVLPosture::Expand || Posture == EVLPosture::Attack))
	{
		LaunchRaid(B);
	}
}

// ------------------------------------------------------------------------------------------------ the home patrol

void FVLCommander::RunPatrol(UVLBattle* B, FVLSquad& S)
{
	UVLCommand* Command = UVLCommand::Get(B);
	TArray<AVLKing*> W;
	FVector C;
	S.Gather(W, C);
	if (!Command || W.Num() == 0)
	{
		return;
	}
	// foes at home: the patrol meets them first (half its reaction time: it is right there)
	const AActor* Castle = B->GetCastle(Team);
	const bool bOnBeat = Castle && FVector::Dist2D(HomeThreatAt, Castle->GetActorLocation()) < Prof.PatrolRadius + 2500.f;
	const bool bThreat = bOnBeat && HomeThreat > 0.2f && ThreatSince >= 0.f && (Clock - ThreatSince >= Prof.ReactionDelay * 0.5f || Posture == EVLPosture::Defend);
	if (bThreat)
	{
		if (S.Task != EVLSquadTask::Defend)
		{
			SetTask(S, EVLSquadTask::Defend, FString::Printf(TEXT("foes at home (%.1f)"), HomeThreat));
		}
		SetStance(W, EVLStance::Aggressive);
		if (S.OrderedFor != S.MemberHash() || FVector::Dist2D(S.OrderedGoal, HomeThreatAt) > 1000.f || (!AnyEngaged(W) && Clock - S.LastOrder > 5.f))
		{
			MarchTo(B, S, HomeThreatAt, true, EVLFormation::Line);
		}
		S.Goal = HomeThreatAt;
		return;
	}
	TArray<FVector> Pts;
	PatrolPoints(B, Pts);
	if (S.Task != EVLSquadTask::Patrol)
	{
		SetTask(S, EVLSquadTask::Patrol, FString::Printf(TEXT("round the base (%d points)"), Pts.Num()));
	}
	S.Goal = Pts.Num() ? Pts[0] : C;
	// (the loop again when its members or its points change, or the patrol was broken off)
	bool bChanged = Pts.Num() != S.Via.Num();
	for (int32 i = 0; !bChanged && i < Pts.Num(); ++i)
	{
		bChanged = FVector::Dist2D(Pts[i], S.Via[i]) > 500.f;
	}
	TArray<FVector> Route;
	bool bLoop = false;
	int32 Next = 0;
	const bool bOnRoute = Command->GetRoute(W[0], Route, bLoop, Next) && bLoop;
	if ((bChanged || !bOnRoute || S.OrderedFor != S.MemberHash()) && !AnyEngaged(W) && Clock - S.LastOrder > 3.f && Pts.Num() > 0)
	{
		SetStance(W, EVLStance::Defensive);
		Command->OrderPatrol(W, Pts, false, EVLFormation::Column);
		S.Via = Pts;
		S.OrderedFor = S.MemberHash();
		S.LastOrder = Clock;
	}
}

// ------------------------------------------------------------------------------------------------ the guard

void FVLCommander::RunGuard(UVLBattle* B, FVLSquad& S)
{
	UVLCommand* Command = UVLCommand::Get(B);
	AActor* Castle = B->GetCastle(Team);
	TArray<AVLKing*> W;
	FVector C;
	S.Gather(W, C);
	if (!Command || !Castle || W.Num() == 0)
	{
		return;
	}
	if (S.Task != EVLSquadTask::Guard)
	{
		SetTask(S, EVLSquadTask::Guard, TEXT("the castle"));
	}
	S.Goal = Castle->GetActorLocation();
	// its wards: Builders working far from the castle (BuilderGuards each), on Hard its furthest mine on its half, the
	// castle
	TArray<TPair<AActor*, int32>> Wards;
	int32 Left = W.Num();
	// (the healthiest go out to the far wards; the hurt stay by the castle)
	W.Sort([](const AVLKing& X, const AVLKing& Y) { return X.GetHealthFrac() > Y.GetHealthFrac(); });
	if (Prof.BuilderGuards > 0)
	{
		TArray<AVLKing*> Builders;
		if (UVLConstruction* Cn = UVLConstruction::Get(B))
		{
			Cn->GetBuilders(Team, Builders);
		}
		for (AVLKing* Bd : Builders)
		{
			const UVLBuilderWork* Work = UVLBuilderWork::For(Bd, false);
			const AActor* Job = Work ? Work->GetJob() : nullptr;
			if (Job && B->DistanceTo(Castle, Job->GetActorLocation()) > 3500.f && Left > 1 && W[0]->GetHealthFrac() > 0.5f)
			{
				const int32 N = FMath::Min(Prof.BuilderGuards, Left - 1);
				Wards.Add({ Bd, N });
				Left -= N;
			}
		}
	}
	if (Prof.GuardMax >= 4 && Left >= 4)
	{
		const FVLBuildingState* Far = nullptr;
		for (const FVLBuildingState& Bs : B->GetBuildings())
		{
			if (Bs.Team == Team && Bs.IsAlive() && Bs.Kind == EVLBuilding::Mine && B->DistanceTo(Castle, Bs.Rest) < Prof.PatrolRadius * 1.4f
				&& (Team == 0 ? Map.AlongOf(Bs.Rest) : 1.f - Map.AlongOf(Bs.Rest)) < 0.42f
				&& (!Far || FVector::Dist2D(Bs.Rest, Castle->GetActorLocation()) > FVector::Dist2D(Far->Rest, Castle->GetActorLocation())))
			{
				Far = &Bs;
			}
		}
		if (Far && B->DistanceTo(Castle, Far->Rest) > 4000.f && W.Num() > 1 && W[1]->GetHealthFrac() > 0.5f)
		{
			Wards.Add({ Far->Actor.Get(), 2 });
			Left -= 2;
		}
	}
	Wards.Add({ Castle, Left });
	// those already on the right ward keep their posts; the others are posted (all of a ward's together)
	TMap<AActor*, TArray<AVLKing*>> Want;
	TSet<AVLKing*> Placed;
	for (const TPair<AActor*, int32>& Wd : Wards)
	{
		TArray<AVLKing*>& Mine = Want.FindOrAdd(Wd.Key);
		for (AVLKing* U : W)
		{
			if (Mine.Num() < Wd.Value && !Placed.Contains(U) && Command->GuardWardOf(U) == Wd.Key)
			{
				Mine.Add(U);
				Placed.Add(U);
			}
		}
	}
	for (const TPair<AActor*, int32>& Wd : Wards)
	{
		TArray<AVLKing*>& Mine = Want.FindOrAdd(Wd.Key);
		TArray<AVLKing*> New;
		for (AVLKing* U : W)
		{
			if (Mine.Num() + New.Num() < Wd.Value && !Placed.Contains(U))
			{
				New.Add(U);
				Placed.Add(U);
			}
		}
		if (New.Num() > 0)
		{
			for (AVLKing* U : New)
			{
				if (!VLAI::Engaged(U))
				{
					U->Stance = EVLStance::Defensive;
				}
			}
			New.RemoveAll([](AVLKing* U) { return VLAI::Engaged(U); });     // (finishes its fight first)
			if (New.Num() > 0)
			{
				const int32 Posted = Command->OrderGuard(New, Wd.Key);
				const FVLBuildingState* WS = B->FindBuilding(Wd.Key);
				UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] Guard#%d posts %d at %s"), Team, *Clk(Clock), S.Id, Posted, WS ? *WS->Name : *Cast<AVLKing>(Wd.Key)->GetDisplayName());
			}
		}
	}
}

// ------------------------------------------------------------------------------------------------ the field army

void FVLCommander::HoldAt(UVLBattle* B, FVLSquad& S, const FVector& InWhere, const FString& Name)
{
	const FVector Where = OutOfReach(B, InWhere);
	TArray<AVLKing*> W;
	FVector C;
	S.Gather(W, C);
	if (S.Task != EVLSquadTask::Hold || S.GoalName != Name || FVector::Dist2D(S.Goal, Where) > 1000.f)
	{
		SetTask(S, EVLSquadTask::Hold, Name);
		S.Via.Reset();
	}
	S.Goal = Where;
	if (W.Num() == 0 || AnyEngaged(W))
	{
		return;                 // (they finish the fight first)
	}
	int32 Far = 0;
	bool bWalking = false;
	for (AVLKing* U : W)
	{
		Far += FVector::Dist2D(U->GetFeet(), Where) > 2200.f + 120.f * W.Num() ? 1 : 0;
		bWalking |= U->HasOrder();
	}
	const bool bNew = (S.OrderedFor != S.MemberHash() && Clock - S.LastOrder > 10.f) || FVector::Dist2D(S.OrderedGoal, Where) > 600.f;
	if (bNew || (Far > 0 && !bWalking && Clock - S.LastOrder > 8.f))
	{
		SetStance(W, EVLStance::Defensive);
		MarchTo(B, S, Where, Far > W.Num() / 2 && FVector::Dist2D(C, Where) > 6000.f, EVLFormation::Line);
	}
}

AActor* FVLCommander::PlanAttack(UVLBattle* B, TArray<AVLKing*>& OutBody, FVector& OutFrom, float& OutPower, float& OutDefence)
{
	OutBody.Reset();
	OutFrom = MusterPoint(B);
	OutPower = OutDefence = 0.f;
	FVector Sum = FVector::ZeroVector;
	for (const FVLSquad& S : Squads)
	{
		if (S.Role != EVLSquadRole::Field && S.Role != EVLSquadRole::Picket)
		{
			continue;
		}
		for (const TWeakObjectPtr<AVLKing>& U : S.Units)
		{
			if (U.IsValid() && U->IsAlive() && !VLAI::Engaged(U.Get()))
			{
				OutBody.Add(U.Get());
				Sum += U->GetFeet();
			}
		}
	}
	if (OutBody.Num() == 0)
	{
		return nullptr;
	}
	OutFrom = Sum / OutBody.Num();
	const int32 Cap = FMath::Min3(Prof.AttackCap + Prof.AttackCapGrowth * WavesSent, Prof.AttackCapMax, WaveSizeMax);
	OutBody.Sort([](const AVLKing& X, const AVLKing& Y) { return X.GetHealthFrac() > Y.GetHealthFrac(); });
	if (OutBody.Num() > Cap && !FinalPush())        // (the final push: everyone it can spare)
	{
		OutBody.SetNum(Cap);
	}
	OutPower = SumPower(OutBody);
	// the best target, the foe on the way to it counted too (up to three tried)
	TArray<const AActor*> Skip;
	for (int32 Try = 0; Try < 3; ++Try)
	{
		float Defence = 0.f;
		AActor* T = PickTarget(B, OutFrom, OutPower, false, &Defence, &Skip);
		if (!T)
		{
			break;
		}
		const float OnTheWay = RouteDefence(B, OutFrom, AttackSpot(B, T)) * 0.8f;
		if (OnTheWay <= Defence * 1.3f || OutPower >= OnTheWay * Prof.Advantage || (FinalPush() && T == B->GetCastle(Foe())))
		{
			OutDefence = FMath::Max(Defence, OnTheWay);
			return T;
		}
		if (VLAIDebugLevel() >= 1)
		{
			UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] passes over %s: %.1f on the way to it against %.1f there"), Team, *Clk(Clock), B->FindBuilding(T) ? *B->FindBuilding(T)->Name : *T->GetName(), OnTheWay, Defence);
		}
		Skip.Add(T);
	}
	return nullptr;
}

bool FVLCommander::LaunchAttack(UVLBattle* B, FVLSquad& Field)
{
	const int32 FieldId = Field.Id;     // (SquadFor below may move the array: the squad is found again by its id)
	// the body and the target the strategy weighed (the field army's and its picket's free troops, up to the cap): the
	// rest of the field army waits in reserve
	TArray<AVLKing*> Free;
	FVector C;
	float Power = 0.f, Defence = 0.f;
	AActor* Target = PlanAttack(B, Free, C, Power, Defence);
	if (Field.Target.IsValid() && B->IsAlive(Field.Target.Get()))
	{
		Target = Field.Target.Get();     // (after its flank: the same target)
		Defence = ExpectedDefence(B, Target->GetActorLocation(), false);
	}
	if (!Target || Free.Num() < MinAttackSize)
	{
		return false;
	}
	// the final push on the castle: the patrol, the picket, the reserve and all but two of the guard go too
	const bool bAllIn = FinalPush() && Target == B->GetCastle(Foe()) && !Field.Target.IsValid();
	if (bAllIn)
	{
		for (FVLSquad& Sq : Squads)
		{
			if (Sq.Role != EVLSquadRole::Patrol && Sq.Role != EVLSquadRole::Picket && Sq.Role != EVLSquadRole::Reserve && Sq.Role != EVLSquadRole::Guard)
			{
				continue;
			}
			TArray<AVLKing*> SW;
			FVector SC;
			Sq.Gather(SW, SC);
			SW.Sort([](const AVLKing& X, const AVLKing& Y) { return X.GetHealthFrac() < Y.GetHealthFrac(); });     // (the guard keeps its most hurt)
			const int32 Keep = Sq.Role == EVLSquadRole::Guard ? FMath::Min(2, SW.Num()) : 0;
			for (int32 i = Keep; i < SW.Num(); ++i)
			{
				if (!VLAI::Engaged(SW[i]) && SW[i]->GetHealthFrac() > 0.5f && !Free.Contains(SW[i]))
				{
					Free.Add(SW[i]);
					Sq.Units.Remove(SW[i]);
				}
			}
		}
		Power = SumPower(Free);
	}
	// the picket's chosen ones join the field army; the field army's others wait in reserve
	for (FVLSquad& Sq : Squads)
	{
		if (Sq.Role == EVLSquadRole::Picket)
		{
			Sq.Units.RemoveAll([&Free](const TWeakObjectPtr<AVLKing>& U) { return Free.Contains(U.Get()); });
		}
	}
	for (AVLKing* U : Free)
	{
		if (!Field.Has(U))
		{
			Field.Units.Add(U);
		}
	}
	TArray<AVLKing*> Extra;
	for (const TWeakObjectPtr<AVLKing>& U : Field.Units)
	{
		if (U.IsValid() && !Free.Contains(U.Get()) && !VLAI::Engaged(U.Get()))
		{
			Extra.Add(U.Get());
		}
	}
	// go when the odds are good; once the army is at its housing cap there is nothing to gain by waiting
	const bool bMaxed = B->GetPopulation(Team) >= B->GetPopulationCap(Team) - 1;
	const bool bGood = Power >= Defence * Prof.Advantage;
	const bool bWaitedLong = Prof.bImpatient && Clock > NextWaveTime + 150.f && Power >= Defence * 0.85f;
	const bool bPush = FinalPush() && Target == B->GetCastle(Foe()) && Free.Num() >= AttackWant(B);
	if (!bGood && !bMaxed && !bWaitedLong && !bPush && !Field.Target.IsValid())
	{
		return false;
	}
	// in force: the wave's size, unless its housing is full or the odds are overwhelming (AttackWant)
	if (!Field.Target.IsValid() && !bMaxed && Free.Num() < AttackWant(B) && Power < Defence * 2.f * Prof.Advantage)
	{
		return false;
	}
	const FVector Goal = AttackSpot(B, Target);
	const FVLBuildingState* TS = B->FindBuilding(Target);
	const FString TName = TS ? TS->Name : Target->GetName();
	// ---- Hard: a second body round by a flank bridge, the main body leaving later so that both arrive together
	if (Prof.bFlank && !bAllIn && Free.Num() >= 8 && !FindSquad(EVLSquadRole::Flank) && !Field.Target.IsValid())
	{
		const float Direct = VLAI::RouteLength(B, C, Goal);
		const FVLAIPoint* Best = nullptr;
		float BestLen = Direct * 1.7f;
		for (const FVLAIPoint& P : Map.Points)
		{
			if (P.Kind != EVLAIPoint::Flank || (Prof.bAvoidTowers && InFoeReach(B, P.End[Foe()], 300.f)))
			{
				continue;
			}
			const float Len = VLAI::RouteLength(B, C, P.End[Team]) + float(FVector::Dist2D(P.End[Team], P.End[Foe()])) + VLAI::RouteLength(B, P.End[Foe()], Goal);
			if (Len < BestLen)
			{
				BestLen = Len;
				Best = &P;
			}
		}
		if (Best)
		{
			// swordsmen first (they take the walls), a third to two fifths of the body
			Free.Sort([](const AVLKing& X, const AVLKing& Y) { return int32(X.IsRanged()) < int32(Y.IsRanged()); });
			const int32 NFlank = FMath::Clamp(FMath::RoundToInt(Free.Num() * 0.4f), 3, Free.Num() - MinAttackSize);
			FVLSquad& Flank = SquadFor(EVLSquadRole::Flank);
			FVLSquad& F = *Squads.FindByPredicate([FieldId](const FVLSquad& X) { return X.Id == FieldId; });
			for (int32 i = 0; i < NFlank; ++i)
			{
				F.Units.Remove(Free[i]);
				Flank.Units.Add(Free[i]);
				Free[i]->Stance = EVLStance::Aggressive;
			}
			Flank.Target = Target;
			Flank.ProgressAt = Clock;
			Flank.ProgressDealt = -1.f;
			Flank.Via = { Best->End[Team], Best->End[Foe()] };
			Flank.StartSize = NFlank;
			Flank.LastFight = Clock;
			TArray<AVLKing*> FW;
			FVector FC;
			Flank.Gather(FW, FC);
			Flank.StartPower = SumPower(FW);
			SetTask(Flank, EVLSquadTask::Attack, FString::Printf(TEXT("%s round by %s"), *TName, *Best->Name));
			Flank.Goal = Goal;
			MarchTo(B, Flank, Goal, true, EVLFormation::Column);
			// the main body waits for the flank to get ahead, then goes at the same target
			F.Target = Target;
			F.Departs = Clock + FMath::Clamp((BestLen - Direct) / 760.f, 0.f, 45.f);
			UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] flank: %d troops to %s round by %s (%.0f m against %.0f m); the main body leaves in %.0f s"), Team, *Clk(Clock), NFlank, *TName, *Best->Name,
				BestLen / 100.f, Direct / 100.f, F.Departs - Clock);
			++WavesSent;
			NextWaveTime = Clock + WaveHeld;
			return true;
		}
	}
	// ---- the attack
	for (AVLKing* U : Extra)
	{
		Field.Units.Remove(U);
	}
	if (Extra.Num() > 0)
	{
		FVLSquad& Res = SquadFor(EVLSquadRole::Reserve);
		for (AVLKing* U : Extra)
		{
			Res.Units.Add(U);
		}
	}
	FVLSquad& F = *Squads.FindByPredicate([FieldId](const FVLSquad& X) { return X.Id == FieldId; });
	TArray<AVLKing*> Go;
	FVector GC;
	F.Gather(Go, GC);
	SetStance(Go, EVLStance::Aggressive);
	F.Target = Target;
	F.TargetHealth = -1.f;
	F.ProgressAt = Clock;
	F.ProgressDealt = -1.f;
	F.StartSize = Go.Num();
	F.StartPower = SumPower(Go);
	F.LastFight = Clock;
	F.Via.Reset();
	SetTask(F, EVLSquadTask::Attack, TName);
	F.Goal = Goal;
	MarchTo(B, F, Goal, true, EVLFormation::Line);
	const bool bFollowsFlank = F.Departs > 0.f;
	F.Departs = 0.f;
	if (!bFollowsFlank)
	{
		++WavesSent;
	}
	NextWaveTime = Clock + WaveHeld;        // set for real when this attack ends
	UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] attacks (#%d): %d troops, power %.1f vs expected %.1f at %s%s"), Team, *Clk(Clock), WavesSent, Go.Num(), F.StartPower, Defence, *TName,
		bFollowsFlank ? TEXT(" [after its flank]") : (bGood ? TEXT("") : (bMaxed ? TEXT(" [maxed]") : TEXT(" [impatient]"))));
	return true;
}

void FVLCommander::RunField(UVLBattle* B, FVLSquad& S)
{
	TArray<AVLKing*> W;
	FVector C;
	S.Gather(W, C);
	if (W.Num() == 0)
	{
		if (S.IsOut())
		{
			StepAttack(B, S);       // (wiped out: it ends)
		}
		return;
	}
	const float Power = SumPower(W);
	const AActor* Castle = B->GetCastle(Team);
	// ---- out on an attack: it goes on, unless the home needs it or the strategy calls it back
	if (S.Task == EVLSquadTask::Attack)
	{
		if (Posture == EVLPosture::Defend)
		{
			const FVLBuildingState* T = B->FindBuilding(S.Target.Get());
			const bool bClose = Castle && FVector::Dist2D(C, Castle->GetActorLocation()) < 7000.f;
			const bool bCastleThreat = Castle && B->DistanceTo(Castle, HomeThreatAt) < 3200.f;
			const bool bWinning = T && T->IsAlive() && T->Health / FMath::Max(T->MaxHealth, 1.f) < (T->Kind == EVLBuilding::Castle ? 0.45f : 0.3f) && LocalFoePower(B, C, 2000.f) < Power * 0.5f;
			if ((bClose || bCastleThreat) && !bWinning)
			{
				UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] recalls its attack to defend (threat %.1f)"), Team, *Clk(Clock), HomeThreat);
				NextWaveTime = Clock + Prof.Regroup * 0.5f;
				SetTask(S, EVLSquadTask::Defend, TEXT("recalled home"));
				MarchTo(B, S, HomeThreatAt, true, EVLFormation::Line);
				return;
			}
		}
		if (Posture == EVLPosture::Regroup)
		{
			EndAttack(B, S, TEXT("regroup"));
			return;
		}
		StepAttack(B, S);
		return;
	}
	// ---- falling back: until it is home (or has walked long enough)
	if (S.Task == EVLSquadTask::Retreat)
	{
		bool bAllIdle = true;
		for (AVLKing* U : W)
		{
			bAllIdle &= VLAI::Idle(U);
		}
		if (FVector::Dist2D(C, S.Goal) < 2000.f || (bAllIdle && Clock - S.TaskSince > 6.f) || Clock - S.TaskSince > 45.f)
		{
			HoldAt(B, S, SafePoint(B), TEXT("regrouping under its towers"));
		}
		return;
	}
	// ---- after a foe body caught in the open: until it is beaten, gone, or too strong
	if (S.Task == EVLSquadTask::Intercept)
	{
		const float Theirs = LocalFoePower(B, C, 2500.f);
		const FVLFoeGroup* G = nullptr;
		for (const FVLFoeGroup& X : FoeGroups)
		{
			if (FVector::Dist2D(X.Centre, S.Goal) < 3500.f && (!G || X.Power > G->Power))
			{
				G = &X;
			}
		}
		if (Theirs > 0.f && Power < Theirs * Prof.RetreatHold)
		{
			SetTask(S, EVLSquadTask::Retreat, TEXT("the foe body is too strong"));
			S.Goal = SafePoint(B);
			MarchTo(B, S, S.Goal, true, EVLFormation::Column, false);
			return;
		}
		if (!G || Clock - S.TaskSince > 45.f || (Prof.bAvoidTowers && InFoeReach(B, G->Centre, 0.f)))
		{
			if (!AnyEngaged(W))
			{
				SetTask(S, EVLSquadTask::Idle, TEXT("interception over"));
			}
			return;
		}
		if (FVector::Dist2D(S.OrderedGoal, G->Centre) > 1200.f && !AnyEngaged(W))
		{
			S.Goal = G->Centre;
			MarchTo(B, S, G->Centre, true, EVLFormation::Line);
		}
		return;
	}
	// ---- the posture's task
	switch (Posture)
	{
	case EVLPosture::Defend:
		if (ThreatSince >= 0.f || Clock - LastFoeAttack < 3.f)
		{
			if (S.Task != EVLSquadTask::Defend)
			{
				SetTask(S, EVLSquadTask::Defend, FString::Printf(TEXT("foes at home (%.1f)"), HomeThreat));
			}
			SetStance(W, EVLStance::Aggressive);
			S.Goal = HomeThreatAt;
			if (S.OrderedFor != S.MemberHash() || FVector::Dist2D(S.OrderedGoal, HomeThreatAt) > 1200.f || (!AnyEngaged(W) && Clock - S.LastOrder > 6.f))
			{
				MarchTo(B, S, HomeThreatAt, true, EVLFormation::Line);
			}
			return;
		}
		HoldAt(B, S, MusterPoint(B), TEXT("in front of the castle"));
		return;
	case EVLPosture::Attack:
		if (Clock >= S.Departs && LaunchAttack(B, S))
		{
			return;
		}
		break;
	case EVLPosture::Regroup:
		HoldAt(B, S, SafePoint(B), TEXT("regrouping under its towers"));
		return;
	default:
		break;
	}
	// (a main body waiting for its flank holds where it is)
	if (S.Departs > 0.f && FindSquad(EVLSquadRole::Flank))
	{
		if (Clock >= S.Departs)
		{
			LaunchAttack(B, S);
		}
		return;
	}
	S.Departs = 0.f;
	S.Target.Reset();
	// ---- a foe body caught in the open, within its reach, that it clearly outmatches: go for it
	if (Prof.InterceptOdds > 0.f)
	{
		const FVLFoeGroup* Best = nullptr;
		for (const FVLFoeGroup& G : FoeGroups)
		{
			if (G.bExposed && !G.bAtOurHome && FVector::Dist2D(G.Centre, C) < Prof.InterceptRange && Power >= G.Power * Prof.InterceptOdds && (!Best || G.Power > Best->Power))
			{
				Best = &G;
			}
		}
		if (Best)
		{
			++Stat[3];
			SetTask(S, EVLSquadTask::Intercept, FString::Printf(TEXT("a foe body of %d caught in the open (%.1f vs %.1f)"), Best->Count, Power, Best->Power));
			S.Goal = Best->Centre;
			SetStance(W, EVLStance::Aggressive);
			MarchTo(B, S, Best->Centre, true, EVLFormation::Line);
			return;
		}
	}
	// ---- holding: the contested point, else its side of the crossing
	if (Posture == EVLPosture::Contest && Map.Points.IsValidIndex(ContestPoint))
	{
		FVector At;
		float Score = 0.f;
		const int32 P = PickContest(B, Power, &At, &Score);
		if (P != INDEX_NONE)
		{
			HoldAt(B, S, At, FString::Printf(TEXT("holding %s"), *Map.Points[P].Name));
			return;
		}
	}
	FString Name;
	const FVector Fwd = ForwardPoint(B, &Name);
	HoldAt(B, S, Fwd, FString::Printf(TEXT("holding %s"), *Name));
}

void FVLCommander::RunReserve(UVLBattle* B, FVLSquad& S)
{
	TArray<AVLKing*> W;
	FVector C;
	S.Gather(W, C);
	if (W.Num() == 0)
	{
		return;
	}
	// foes at home: it is the home's reserve
	if (HomeThreat > 0.2f && ThreatSince >= 0.f && Clock - ThreatSince >= Prof.ReactionDelay)
	{
		if (S.Task != EVLSquadTask::Defend)
		{
			SetTask(S, EVLSquadTask::Defend, TEXT("foes at home"));
		}
		if (FVector::Dist2D(S.OrderedGoal, HomeThreatAt) > 1200.f || (!AnyEngaged(W) && Clock - S.LastOrder > 6.f))
		{
			MarchTo(B, S, HomeThreatAt, true, EVLFormation::Line);
		}
		return;
	}
	// reinforce an attack that is going well, as a body (a trickle of three dies to the first tower on the way)
	FVLSquad* Field = FindSquad(EVLSquadRole::Field);
	if (Field && Field->Task == EVLSquadTask::Attack && Prof.bReinforce && W.Num() >= (IsPushing(B) ? 10 : 5) && Clock - LastReinforce > 20.f)     // (the push: in tens, not a trickle of five into the grinder)
	{
		TArray<AVLKing*> FW;
		FVector FC;
		Field->Gather(FW, FC);
		const float Ours = SumPower(FW), Theirs = LocalFoePower(B, FC, 2200.f);
		if (FW.Num() > 0 && Ours > Theirs * 0.9f)
		{
			LastReinforce = Clock;
			SetStance(W, EVLStance::Aggressive);
			UVLCommand::Get(B)->OrderAttackMove(W, FC, true, EVLFormation::Column);
			UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] reinforces its attack with %d"), Team, *Clk(Clock), W.Num());
			Field->StartSize += W.Num();
			Field->StartPower += SumPower(W);
			MergeInto(S, *Field);
			return;
		}
	}
	FString Name;
	const FVector Fwd = ForwardPoint(B, &Name);
	HoldAt(B, S, Fwd, FString::Printf(TEXT("the reserve, holding %s"), *Name));
}

bool FVLCommander::PicketPoint(UVLBattle* B, FVector& OutAt, FString& OutName) const
{
	const AActor* Castle = B->GetCastle(Team);
	const FVLSquad* Field = Squads.FindByPredicate([](const FVLSquad& S) { return S.Role == EVLSquadRole::Field; });
	if (!Castle || !Field)
	{
		return false;
	}
	const FVector Home = Castle->GetActorLocation();
	float Best = 0.f;
	auto Consider = [&](const FVector& P, float Value, const FString& Name)
	{
		const float Along = Team == 0 ? Map.AlongOf(P) : 1.f - Map.AlongOf(P);
		if (Along > 0.6f || FVector::Dist2D(P, Field->Goal) < 4000.f || FVector::Dist2D(P, Home) < 3500.f || (Prof.bAvoidTowers && InFoeReach(B, P, 400.f)))
		{
			return;
		}
		const float Score = Value / (1.f + float(FVector::Dist2D(P, Home)) / 25000.f);
		if (Score > Best)
		{
			Best = Score;
			OutAt = P;
			OutName = Name;
		}
	};
	for (const FVLAIPoint& P : Map.Points)
	{
		if (P.Kind == EVLAIPoint::Flank)
		{
			Consider(VLAI::Snap(B, P.End[Team] + (Home - P.End[Team]).GetSafeNormal2D() * 700.f, 20), 0.75f, TEXT("its end of ") + P.Name);
		}
		else if (P.Kind == EVLAIPoint::Vein)
		{
			const FVLBuildingState* S = B->FindBuilding(P.Actor.Get());
			const bool bOurs = S && S->IsAlive() && S->Team == Team;
			if (bOurs || VLAI::IsFreeVein(B, P.Actor.Get()))
			{
				Consider(VLAI::Snap(B, P.Pos + (Home - P.Pos).GetSafeNormal2D() * 1400.f, 20), bOurs ? 0.65f : 0.45f, bOurs ? TEXT("its claimed mine") : P.Name);
			}
		}
	}
	// its own outlying mines (the level's), beyond the patrol's beat
	for (const FVLBuildingState& S : B->GetBuildings())
	{
		if (S.Team == Team && S.IsWorking() && S.Kind == EVLBuilding::Mine && B->DistanceTo(Castle, S.Rest) > Prof.PatrolRadius)
		{
			FVector Door, Rally, Front;
			B->FrontOf(S.Actor.Get(), Door, Rally, Front);
			Consider(VLAI::Snap(B, Rally, 20), 0.55f, TEXT("its outlying mine"));
		}
	}
	return Best > 0.f;
}

void FVLCommander::RunPicket(UVLBattle* B, FVLSquad& S)
{
	TArray<AVLKing*> W;
	FVector C;
	S.Gather(W, C);
	if (W.Num() == 0)
	{
		return;
	}
	// foes at home (the whole army turns round), or a foe body at its post: it fights there
	if (Posture == EVLPosture::Defend && HomeThreat > 0.2f && Clock - LastFoeAttack < 3.f && FVector::Dist2D(C, HomeThreatAt) < 9000.f)
	{
		if (S.Task != EVLSquadTask::Defend)
		{
			SetTask(S, EVLSquadTask::Defend, TEXT("foes at home"));
		}
		if (FVector::Dist2D(S.OrderedGoal, HomeThreatAt) > 1200.f || (!AnyEngaged(W) && Clock - S.LastOrder > 6.f))
		{
			MarchTo(B, S, HomeThreatAt, true, EVLFormation::Line);
		}
		return;
	}
	FVector At;
	FString Name;
	if (!PicketPoint(B, At, Name))
	{
		FString FName;
		At = ForwardPoint(B, &FName);
		Name = FName;
	}
	HoldAt(B, S, At, FString::Printf(TEXT("picket on %s"), *Name));
}

// ------------------------------------------------------------------------------------------------ raids

bool FVLCommander::LaunchRaid(UVLBattle* B)
{
	int32 Out = 0;
	for (const FVLSquad& S : Squads)
	{
		Out += (S.Role == EVLSquadRole::Raid && S.IsOut()) ? 1 : 0;
	}
	if (Out >= Prof.MaxRaids || Clock < NextRaidTime)
	{
		return false;
	}
	// the party comes from the field army while it holds at home, else from the reserve gathering behind an attack
	FVLSquad* Field = FindSquad(EVLSquadRole::Field);
	if (Field && ((Field->Task != EVLSquadTask::Hold && Field->Task != EVLSquadTask::Idle) || Posture == EVLPosture::Attack))
	{
		Field = FindSquad(EVLSquadRole::Reserve);       // (an attack about to leave keeps its strength)
	}
	if (!Field || (Field->Task != EVLSquadTask::Hold && Field->Task != EVLSquadTask::Idle))
	{
		return false;
	}
	const EVLSquadRole FromRole = Field->Role;
	TArray<AVLKing*> W;
	FVector C;
	Field->Gather(W, C);
	TArray<AVLKing*> Free = W.FilterByPredicate([](AVLKing* U) { return !VLAI::Engaged(U) && U->GetHealthFrac() > 0.6f; });
	// only from a surplus; swordsmen first (they hit buildings), the healthiest
	if (Free.Num() < Prof.RaidSize + 2)
	{
		return false;
	}
	Free.Sort([](const AVLKing& X, const AVLKing& Y) { return X.IsRanged() != Y.IsRanged() ? !X.IsRanged() : X.GetHealthFrac() > Y.GetHealthFrac(); });
	Free.SetNum(Prof.RaidSize + (RaidsSent >= 2 && Free.Num() > Prof.RaidSize + 3 ? 1 : 0));
	const FVector From = MusterPoint(B);
	const float RaidPower = SumPower(Free);
	float Defence = 0.f;
	AActor* Target = nullptr;
	{
		// an outlying farm or mine with next to no defence, and not past the foe's castle or army on the way there
		TArray<const AActor*> Skip;
		for (int32 Try = 0; Try < 3 && !Target; ++Try)
		{
			AActor* T = PickTarget(B, From, RaidPower, true, &Defence, &Skip);
			if (!T)
			{
				break;
			}
			const float OnTheWay = RouteDefence(B, C, AttackSpot(B, T));
			if (OnTheWay > RaidPower * 0.7f && !Prof.bFlank)
			{
				UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] passes over raiding %s: %.1f on the way"), Team, *Clk(Clock), B->FindBuilding(T) ? *B->FindBuilding(T)->Name : *T->GetName(), OnTheWay);
				Skip.Add(T);
				continue;
			}
			Target = T;
		}
	}
	if (!Target)
	{
		NextRaidTime = Clock + 15.f;
		return false;
	}
	const FVector Goal = AttackSpot(B, Target);
	// the way with the least of the foe on it: straight, or round by a flank bridge (Hard)
	TArray<FVector> Via;
	FString How = TEXT("straight");
	if (Prof.bFlank)
	{
		TArray<FVector> Route;
		const float Direct = VLAI::RouteLength(B, C, Goal, &Route);     // (B: the one search gives the route and its length; it was run twice)
		float Peak = 0.f;
		const float Risk = Influence.RouteRisk(Route, 1000.f, &Peak);
		for (const FVLAIPoint& P : Map.Points)
		{
			if (P.Kind != EVLAIPoint::Flank)
			{
				continue;
			}
			TArray<FVector> R1, R2;
			const float Len = VLAI::RouteLength(B, C, P.End[Team], &R1) + VLAI::RouteLength(B, P.End[Foe()], Goal, &R2);
			R1.Append(R2);
			float FPeak = 0.f;
			const float FRisk = Influence.RouteRisk(R1, 1000.f, &FPeak);
			if (Len < Direct * 1.8f && FPeak < Peak * 0.6f && FRisk < Risk * 0.7f && Peak > 0.8f)
			{
				Via = { P.End[Team], P.End[Foe()] };
				How = FString::Printf(TEXT("round by %s (risk %.1f against %.1f)"), *P.Name, FRisk, Risk);
				break;
			}
		}
	}
	FVLSquad& Raid = Squads.AddDefaulted_GetRef();
	Raid.Id = NextSquadId++;
	Raid.Role = EVLSquadRole::Raid;
	Field = FindSquad(FromRole);
	for (AVLKing* U : Free)
	{
		Field->Units.Remove(U);
		Raid.Units.Add(U);
		U->Stance = EVLStance::Aggressive;
	}
	const FVLBuildingState* TS = B->FindBuilding(Target);
	Raid.Target = Target;
	Raid.ProgressAt = Clock;
	Raid.StartSize = Free.Num();
	Raid.StartPower = SumPower(Free);
	Raid.LastFight = Clock;
	Raid.Via = Via;
	SetTask(Raid, EVLSquadTask::Raid, TS ? TS->Name : Target->GetName());
	Raid.Goal = Goal;
	MarchTo(B, Raid, Goal, true, EVLFormation::Column);
	++RaidsSent;
	NextRaidTime = Clock + Prof.RaidInterval * (Posture == EVLPosture::Harass ? 0.5f : 1.f);
	UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] raids %s with %d (expected defence %.1f), %s"), Team, *Clk(Clock), TS ? *TS->Name : *Target->GetName(), Free.Num(), Defence, *How);
	return true;
}

// ------------------------------------------------------------------------------------------------ a body that is out

void FVLCommander::EndAttack(UVLBattle* B, FVLSquad& S, const FString& Why)
{
	TArray<AVLKing*> W;
	FVector C;
	S.Gather(W, C);
	const bool bRaid = S.Role == EVLSquadRole::Raid;
	UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] %s#%d %s ends (%s): %d of %d back"), Team, *Clk(Clock), RoleName(S.Role), S.Id, bRaid ? TEXT("raid") : TEXT("attack"), *Why, W.Num(), S.StartSize);
	const FVector Home = SafePoint(B);
	S.Target.Reset();
	S.Via.Reset();
	SetTask(S, EVLSquadTask::Retreat, Why);
	S.Goal = Home;
	if (W.Num() > 0)
	{
		SetStance(W, EVLStance::Defensive);
		MarchTo(B, S, Home, true, EVLFormation::Column, false);       // home, without stopping to fight
	}
	if (bRaid)
	{
		NextRaidTime = FMath::Max(NextRaidTime, Prof.bRaids ? Clock + Prof.RaidInterval * 0.5f : 1e9f);
	}
	else if (S.Role == EVLSquadRole::Field)
	{
		NextWaveTime = Clock + Prof.Regroup;
		// its flank comes back with it
		if (FVLSquad* Flank = FindSquad(EVLSquadRole::Flank); Flank && Flank->IsOut())
		{
			EndAttack(B, *Flank, TEXT("the main body fell back"));
		}
	}
	else if (S.Role == EVLSquadRole::Flank)
	{
		// The flank ended and the main body is not out (it was still waiting for the flank to get ahead, or was called
		// to something else meanwhile): the attack is over. LaunchAttack left NextWaveTime at its "while it is out"
		// mark (Clock + WaveHeld) when the flank set off, and only the main body's own end set it for real: so on
		// Hard, the one difficulty that flanks, the commander never attacked again and the HUD read "Enemy ready in
		// 16650:28" (a million seconds, counting down).
		FVLSquad* Field = FindSquad(EVLSquadRole::Field);
		if (!Field || !Field->IsOut())
		{
			NextWaveTime = Clock + Prof.Regroup;
			if (Field)
			{
				Field->Departs = 0.f;
				Field->Target.Reset();
			}
		}
	}
}

bool FVLCommander::StepAttack(UVLBattle* B, FVLSquad& S)
{
	TArray<AVLKing*> W;
	FVector C;
	S.Gather(W, C);
	const bool bRaid = S.Role == EVLSquadRole::Raid;
	if (W.Num() == 0)
	{
		EndAttack(B, S, TEXT("wiped out"));
		return false;
	}
	// how is the fight where it is going?
	const float Ours = SumPower(W);
	const float Theirs = LocalFoePower(B, C, 2200.f);
	const bool bFighting = AnyEngaged(W);
	if (bFighting || Theirs > 0.f)
	{
		S.LastFight = Clock;
	}
	// losing: fall back and regroup rather than feed the foe one troop at a time (a raid gives up sooner)
	// (the final push, FinalPush: it goes on until it is down to two fifths of what set out)
	const bool bPushing = !bRaid && FinalPush() && S.Target.IsValid() && S.Target.Get() == B->GetCastle(Foe());
	const float Hold = bRaid ? 0.9f : Prof.RetreatHold * (bPushing ? 0.6f : 1.f);
	if (Theirs > 0.f && Ours < Theirs * Hold && (bRaid || W.Num() <= FMath::CeilToInt(S.StartSize * (bPushing ? 0.4f : 0.7f))))
	{
		EndAttack(B, S, FString::Printf(TEXT("outmatched %.1f vs %.1f"), Ours, Theirs));
		return false;
	}
	if (W.Num() <= FMath::CeilToInt(S.StartSize * RetreatFraction) && Theirs > Ours)
	{
		EndAttack(B, S, TEXT("too few left"));
		return false;
	}
	if (Clock - S.LastFight > (bRaid ? 90.f : 150.f))
	{
		EndAttack(B, S, TEXT("no fight"));
		return false;
	}
	// no harm done to the target for long (fights on the way, a hero who keeps rising, a way that does not get there)
	if (const FVLBuildingState* TS = B->FindBuilding(S.Target.Get()))
	{
		// headway: the target hurt, or the side knocking down the foe's other buildings meanwhile
		// (an attack on the castle fights its way through the barracks, farms and towers round it, and its recruits:
		// it was called off as making "no headway" while it razed the foe's base)
		const FVLKingdom& K = B->GetKingdom(Team);
		float Dealt = 0.f;
		for (const float D : K.BuildingDamageBy)
		{
			Dealt += D;
		}
		const bool bDealt = !bRaid && S.ProgressDealt >= 0.f && Dealt > S.ProgressDealt + 1.f && bFighting;
		S.ProgressDealt = Dealt;
		if (S.TargetHealth < 0.f || TS->Health < S.TargetHealth - 1.f || bDealt)
		{
			S.TargetHealth = TS->Health;
			S.ProgressAt = Clock;
		}
		else if (Clock - S.ProgressAt > (bRaid ? 100.f : 160.f))
		{
			EndAttack(B, S, TEXT("no headway"));
			return false;
		}
	}
	// a troop that has made no way for 25 s while it should be walking: stuck; it leaves the attack
	for (AVLKing* U : W)
	{
		const FVector F = U->GetFeet();
		FVector4f* M = Moved.Find(U);
		if (!M || FVector::Dist2D(FVector(M->X, M->Y, M->Z), F) > 300.f || VLAI::Engaged(U))
		{
			Moved.Add(U, FVector4f(float(F.X), float(F.Y), float(F.Z), Clock));
		}
		else if (Clock - M->W > 25.f && B->DistanceTo(S.Target.Get(), F) > 2500.f)
		{
			S.Units.Remove(U);
			Moved.Remove(U);
			// on ground it cannot leave (every route ends where it stands): out of the squads while it is there
			// (left out of the squads while it stands there; if there is a way home it is sent along it, and once it has
			// moved it is a troop like any other again)
			TArray<FVector> Route;
			VLAI::RouteLength(B, F, MusterPoint(B), &Route);
			const bool bTrapped = Route.Num() == 0 || FVector::Dist2D(Route.Last(), F) < 300.f;
			Stuck.Add(U, F);
			if (!bTrapped)
			{
				if (UVLCommand* Cmd = UVLCommand::Get(B))
				{
					Cmd->StopAttack(U);
					Cmd->OrderMove({ U }, MusterPoint(B), false, EVLFormation::Line);
				}
			}
			UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] %s is stuck at (%.0f, %.0f): out of the attack%s"), Team, *Clk(Clock), *U->GetDisplayName(), F.X, F.Y, bTrapped ? TEXT(" (trapped: left out of the squads)") : TEXT(""));
		}
	}
	// a flank near the target before the main body: it waits out of reach until the main body closes in too
	if (S.Role == EVLSquadRole::Flank && S.Target.IsValid())
	{
		const FVLSquad* Main = FindSquad(EVLSquadRole::Field);
		TArray<AVLKing*> MW;
		FVector MC;
		if (Main && Main->Target == S.Target)
		{
			Main->Gather(MW, MC);
		}
		const float DF = B->DistanceTo(S.Target.Get(), C);
		if (MW.Num() > 0 && DF < 5000.f && B->DistanceTo(S.Target.Get(), MC) > DF + 2500.f)
		{
			const FVector WaitAt = OutOfReach(B, C);
			if (!bFighting && FVector::Dist2D(WaitAt, S.OrderedGoal) > 800.f)
			{
				MarchTo(B, S, WaitAt, false, EVLFormation::Line);
				UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] Flank#%d waits for the main body near %s"), Team, *Clk(Clock), S.Id, *S.GoalName);
			}
			S.LastFight = S.ProgressAt = Clock;
			return true;
		}
	}
	// a tower in the way that is not the target: taken down first with enough strength, else the target is dropped.
	// Not on the final push (it goes for the walls: on Realm v2 the east castle's hill tower turned every push aside to a
	// tower it never reached, for fifteen minutes)
	if (Prof.bAvoidTowers && S.Target.IsValid() && !bPushing)
	{
		const AActor* Tower = nullptr;
		if (InFoeReach(B, C, 0.f, &Tower) && Tower && Tower != S.Target.Get() && Tower != B->GetCastle(Foe()))
		{
			const float TowerPower = BuildingPower(B, Tower);
			if (Ours >= TowerPower * 2.2f + LocalFoePower(B, C, 2200.f) - TowerPower && !bRaid)
			{
				const FVLBuildingState* TS = B->FindBuilding(Tower);
				UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] %s#%d takes down %s on its way first (%.1f vs its %.1f)"), Team, *Clk(Clock), RoleName(S.Role), S.Id, TS ? *TS->Name : TEXT("a tower"), Ours, TowerPower);
				S.Target = const_cast<AActor*>(Tower);
				S.TargetHealth = -1.f;
				S.Goal = AttackSpot(B, Tower);
				S.Reorder = 0.f;
			}
			else if (bRaid || Ours < TowerPower * 1.2f)
			{
				EndAttack(B, S, TEXT("a tower in the way"));
				return false;
			}
		}
	}
	// (a siege's picture now and then: how far from the walls, how many fighting, idle, at the walls)
	if (S.Target.IsValid() && S.Target.Get() == B->GetCastle(Foe()) && FMath::Fmod(Clock, 20.f) < Prof.Think)
	{
		int32 NFight = 0, NIdle = 0, NWalls = 0;
		float Near = 1e9f;
		for (AVLKing* U : W)
		{
			NFight += VLAI::Engaged(U) ? 1 : 0;
			NIdle += VLAI::Idle(U) ? 1 : 0;
			const float D = B->DistanceTo(S.Target.Get(), U->GetFeet());
			NWalls += D < 400.f ? 1 : 0;
			Near = FMath::Min(Near, D);
		}
		const FVLBuildingState* CS = B->FindBuilding(S.Target.Get());
		UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] siege: %d troops, middle %.0f m from the castle (nearest %.0f m), %d fighting, %d idle, %d at the walls; castle %.0f; theirs here %.1f, ours %.1f"),
			Team, *Clk(Clock), W.Num(), B->DistanceTo(S.Target.Get(), C) / 100.f, Near / 100.f, NFight, NIdle, NWalls, CS ? CS->Health : -1.f, Theirs, Ours);
	}
	// the target fell: on to the next, chosen from here; at the target with nothing to fight: knock it down
	S.Reorder -= Prof.Think;
	bool bIdle = true;
	for (AVLKing* U : W)
	{
		bIdle &= VLAI::Idle(U);
	}
	UVLCommand* Command = UVLCommand::Get(B);
	if (!S.Target.IsValid() || !B->IsAlive(S.Target.Get()))
	{
		if (bRaid)
		{
			EndAttack(B, S, TEXT("target burned"));        // a raid hits one target and goes home with the news
			return false;
		}
		float Defence = 0.f;
		AActor* Next = PickTarget(B, C, Ours, false, &Defence);
		if (!Next)
		{
			EndAttack(B, S, TEXT("nothing left"));
			return false;
		}
		const FVLBuildingState* NS = B->FindBuilding(Next);
		if (Defence > Ours * 1.25f && NS && NS->Kind != EVLBuilding::Castle)
		{
			EndAttack(B, S, FString::Printf(TEXT("next target too strong %.1f vs %.1f"), Defence, Ours));
			return false;
		}
		S.Target = Next;
		S.TargetHealth = -1.f;
		S.Goal = AttackSpot(B, Next);
		S.Reorder = 6.f;
		S.GoalName = NS ? NS->Name : Next->GetName();
		S.Via.Reset();
		MarchTo(B, S, S.Goal, true, EVLFormation::Line);
		UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] %s#%d moves on to %s"), Team, *Clk(Clock), RoleName(S.Role), S.Id, NS ? *NS->Name : TEXT("?"));
	}
	else if (S.Reorder <= 0.f && Command)
	{
		// the idle ones: at the target, knock it down; still far, march on (a fight on the way stops them a while)
		TArray<AVLKing*> Near, Far;
		for (AVLKing* U : W)
		{
			if (VLAI::Idle(U))
			{
				// (archers knock it down from their reach: 90% of the bow's range)
				const bool bAtGoal = FVector::Dist2D(U->GetFeet(), S.Goal) < 600.f + 60.f * W.Num();
				(bAtGoal || B->DistanceTo(S.Target.Get(), U->GetFeet()) < (U->IsRanged() ? GetDefault<UVLArcherCombat>()->Range * 0.9f : 1500.f) ? Near : Far).Add(U);
			}
		}
		if (Near.Num() > 0)
		{
			Command->OrderAttack(Near, S.Target.Get(), false, false);
			const bool bCastle = S.Target.Get() == B->GetCastle(Foe());
			for (AVLKing* U : Near)
			{
				U->bAutoAttack = true;      // (a foe that comes at them is still answered first)
				U->bSiege = bCastle && !U->IsRanged();     // (swordsmen at the castle: only a foe at their side)
			}
		}
		if (Far.Num() > 0)
		{
			Command->OrderAttackMove(Far, S.Goal, true, EVLFormation::Line);
		}
		S.Reorder = bIdle ? 4.f : 3.f;
	}
	return true;
}

// ------------------------------------------------------------------------------------------------ micro

void FVLCommander::Micro(UVLBattle* B)
{
	for (int32 i = 0; i < Squads.Num(); ++i)
	{
		TArray<AVLKing*> W;
		FVector C;
		Squads[i].Gather(W, C);
		if (W.Num() == 0)
		{
			continue;
		}
		const bool bFight = AnyEngaged(W) || LocalFoePower(B, C, 2600.f) > 0.f;
		if (!bFight)
		{
			continue;
		}
		FocusFire(B, Squads[i], W);
		if (Squads[i].Role != EVLSquadRole::Guard)
		{
			Kite(B, Squads[i], W);
			PullBack(B, Squads[i], W);      // (may add to the guard: Squads may grow)
		}
	}
}

void FVLCommander::FocusFire(UVLBattle* B, FVLSquad& S, const TArray<AVLKing*>& W)
{
	UVLCommand* Command = UVLCommand::Get(B);
	if (Prof.FocusFire <= 0 || !Command)
	{
		return;
	}
	TArray<AVLKing*> Foes;
	B->GetUnits(Foe(), Foes);
	FVector C = FVector::ZeroVector;
	for (AVLKing* U : W)
	{
		C += U->GetFeet();
	}
	C /= W.Num();
	// the squad's one focus: the foe worth most near it (they all lean toward it, so that it falls)
	const AVLKing* Common = nullptr;
	float CommonV = -1e9f;
	TArray<AVLKing*> Near;
	for (AVLKing* F : Foes)
	{
		const float D = float(FVector::Dist2D(F->GetFeet(), C));
		if (D < 4000.f && UVLBattle::IsNoticed(F, D, 4000.f) && UnitPower(F) > 0.f)
		{
			Near.Add(F);
			if (D < 2600.f && FoeValue(F) > CommonV)
			{
				CommonV = FoeValue(F);
				Common = F;
			}
		}
	}
	if (Near.Num() == 0)
	{
		return;
	}
	const float BowRange = GetDefault<UVLArcherCombat>()->Range;
	for (AVLKing* U : W)
	{
		if (!U->IsRanged() && Prof.FocusFire < 2)
		{
			continue;
		}
		const float* Last = Retargeted.Find(U);
		if (Last && Clock - *Last < 2.f)
		{
			continue;
		}
		const float Reach = U->IsRanged() ? (U->IsGarrisoned() ? BowRange * 1.7f : BowRange * 0.95f) : 600.f;
		AVLKing* Best = nullptr;
		float BestV = -1e9f;
		for (AVLKing* F : Near)
		{
			const float D = float(FVector::Dist2D(F->GetFeet(), U->GetFeet()));
			if (D > Reach || (!U->IsRanged() && F->IsGarrisoned()))
			{
				continue;
			}
			const float V = FoeValue(F) + (F == Common ? 0.35f : 0.f) - D / Reach * 0.4f;
			if (V > BestV)
			{
				BestV = V;
				Best = F;
			}
		}
		if (!Best)
		{
			continue;
		}
		AActor* Current = VLAI::FightTarget(U);
		if (Current == Best)
		{
			continue;
		}
		const AVLKing* CurUnit = Cast<AVLKing>(Current);
		bool bSwitch = !Current || !CurUnit;            // idle with a foe in reach, or hitting a wall with a troop at hand
		if (CurUnit && CurUnit->IsAlive())
		{
			const float CurD = float(FVector::Dist2D(CurUnit->GetFeet(), U->GetFeet()));
			const float CurV = CurD > Reach * 1.3f ? -1e9f : FoeValue(CurUnit) + (CurUnit == Common ? 0.35f : 0.f) - CurD / Reach * 0.4f;
			bSwitch = U->IsRanged() ? BestV > CurV + 0.35f
				: (BestV > CurV + 0.5f && FVector::Dist2D(Best->GetFeet(), U->GetFeet()) < 350.f) || CurD > 450.f;
		}
		if (!Current && !VLAI::Engaged(U) && U->HasOrder() && !U->bAttackMove)
		{
			bSwitch = false;        // (on a plain move: going home, a step back; leave it)
		}
		if (!bSwitch)
		{
			continue;
		}
		{
			TGuardValue<bool> Inner(Command->bInnerOrder, true);       // its own doing: the patrol, guard or route goes on
			if (Command->OrderAttack({ U }, Best, false, false) > 0)
			{
				U->bAutoAttack = true;                                  // (let go by its stance as any fight of its own)
				Retargeted.Add(U, Clock);
				++Stat[0];
				if (VLAIDebugLevel() >= 1)
				{
					UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] focus: %s on %s (%.0f%%)"), Team, *Clk(Clock), *U->GetDisplayName(), *Best->GetDisplayName(), Best->GetHealthFrac() * 100.f);
				}
			}
		}
	}
}

void FVLCommander::Kite(UVLBattle* B, FVLSquad& S, const TArray<AVLKing*>& W)
{
	UVLCommand* Command = UVLCommand::Get(B);
	if (!Prof.bKite || !Command)
	{
		return;
	}
	TArray<AVLKing*> Swords;
	for (AVLKing* U : W)
	{
		if (!U->IsRanged())
		{
			Swords.Add(U);
		}
	}
	TArray<AVLKing*> Foes;
	B->GetUnits(Foe(), Foes);
	for (AVLKing* A : W)
	{
		if (!A->IsRanged() || A->IsGarrisoned())
		{
			continue;
		}
		const float* Last = Kited.Find(A);
		if (Last && Clock - *Last < 3.f)
		{
			continue;
		}
		const AVLKing* Threat = nullptr;
		float ThreatD = 450.f;
		for (const AVLKing* F : Foes)
		{
			const float D = float(FVector::Dist2D(F->GetFeet(), A->GetFeet()));
			if (!F->IsRanged() && F->IsTroop() == true && UnitPower(F) > 0.2f && D < ThreatD && FMath::Abs(F->GetFeet().Z - A->GetFeet().Z) < 200.f)
			{
				ThreatD = D;
				Threat = F;
			}
			else if (!F->IsTroop() && D < ThreatD)
			{
				ThreatD = D;
				Threat = F;         // (King David, swinging)
			}
		}
		if (!Threat)
		{
			continue;
		}
		// behind its own swords (they meet the foe that follows); with none near, only a badly hurt archer runs
		const AVLKing* Cover = nullptr;
		for (const AVLKing* Sw : Swords)
		{
			if (FVector::Dist2D(Sw->GetFeet(), A->GetFeet()) < 1500.f && (!Cover || FVector::Dist2D(Sw->GetFeet(), A->GetFeet()) < FVector::Dist2D(Cover->GetFeet(), A->GetFeet())))
			{
				Cover = Sw;
			}
		}
		if (!Cover && A->GetHealthFrac() > 0.5f)
		{
			continue;
		}
		FVector Dir = (A->GetFeet() - Threat->GetFeet()).GetSafeNormal2D();
		if (Cover)
		{
			// past the sword, on the far side of it from the foe
			const FVector Behind = Cover->GetFeet() + (Cover->GetFeet() - Threat->GetFeet()).GetSafeNormal2D() * 400.f;
			Dir = ((Behind - A->GetFeet()).GetSafeNormal2D() + Dir * 0.5f).GetSafeNormal2D();
		}
		if (Dir.IsNearlyZero())
		{
			continue;
		}
		const FVector To = VLAI::Snap(B, A->GetFeet() + Dir * 750.f, 6);
		Command->StopAttack(A);
		{
			TGuardValue<bool> Inner(Command->bInnerOrder, true);
			Command->OrderMove({ A }, To, true, EVLFormation::Line);
		}
		A->Post = To;
		Kited.Add(A, Clock);
		++Stat[1];
		if (VLAIDebugLevel() >= 1)
		{
			UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] kite: %s steps back from %s (%.0f cm)%s"), Team, *Clk(Clock), *A->GetDisplayName(), *Threat->GetDisplayName(), ThreatD, Cover ? TEXT(" behind the swords") : TEXT(""));
		}
	}
}

void FVLCommander::PullBack(UVLBattle* B, FVLSquad& S, const TArray<AVLKing*>& W)
{
	UVLCommand* Command = UVLCommand::Get(B);
	AActor* Castle = B->GetCastle(Team);
	if (Prof.PullBack <= 0.f || !Command || !Castle || W.Num() < 2)
	{
		return;
	}
	if (S.Role == EVLSquadRole::Field && S.Task == EVLSquadTask::Attack && FinalPush() && S.Target.Get() == B->GetCastle(Foe()))
	{
		return;         // (the final push fights it out: the hurt walking 500 m home bled every siege away)
	}
	const double Now = B->GetWorld()->GetTimeSeconds();
	const int32 SquadId = S.Id;
	for (AVLKing* U : W)
	{
		if (U->GetHealthFrac() >= Prof.PullBack || !(VLAI::Engaged(U) || Now - U->LastStruckTime < 3.0))
		{
			continue;
		}
		FVLSquad* From = Squads.FindByPredicate([SquadId](const FVLSquad& X) { return X.Id == SquadId; });
		if (!From)
		{
			return;
		}
		From->Units.Remove(U);
		Command->StopAttack(U);
		// an archer up a tower with room (it shoots from there at twice the reach), else to guard the castle
		AActor* Tower = nullptr;
		if (U->IsRanged())
		{
			for (const FVLBuildingState& Bs : B->GetBuildings())
			{
				if (Bs.Team == Team && Bs.IsWorking() && UVLCommand::IsTower(Bs.Actor.Get()) && Command->TowerCount(Bs.Actor.Get()) < Command->TowerCapacity(Bs.Actor.Get())
					&& FVector::Dist2D(Bs.Rest, U->GetFeet()) < 7000.f)
				{
					Tower = Bs.Actor.Get();
					break;
				}
			}
		}
		if (Tower)
		{
			Command->OrderGarrison({ U }, Tower, true);
		}
		else
		{
			SquadFor(EVLSquadRole::Guard).Units.Add(U);
			U->Stance = EVLStance::Defensive;
			Command->OrderGuard({ U }, Castle);
		}
		++Stat[2];
		UE_LOG(LogVoxelLab, Log, TEXT("AI %d [%s] pulls %s (%.0f%%) out of the fight: %s"), Team, *Clk(Clock), *U->GetDisplayName(), U->GetHealthFrac() * 100.f, Tower ? TEXT("up a tower") : TEXT("to guard the castle"));
	}
}
