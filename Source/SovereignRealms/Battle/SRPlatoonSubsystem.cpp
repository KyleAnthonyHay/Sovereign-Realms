// Copyright Sovereign Realms.

#include "Battle/SRPlatoonSubsystem.h"
#include "Battle/SRBattleSubsystem.h"
#include "Battle/SREconomySubsystem.h"
#include "Units/SRUnit.h"
#include "Common/SRFeelSettings.h"
#include "SovereignRealms.h"
#include "Engine/World.h"

#define LOCTEXT_NAMESPACE "SRPlatoons"

USRPlatoonSubsystem* USRPlatoonSubsystem::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	return World ? World->GetSubsystem<USRPlatoonSubsystem>() : nullptr;
}

bool USRPlatoonSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void USRPlatoonSubsystem::Reset()
{
	Platoons.Reset();
	Platoons.SetNum(FMath::Clamp(USRFeelSettings::Get().MaxPlatoons, 1, 9));
}

void USRPlatoonSubsystem::Prune(FSRPlatoon& P)
{
	for (int32 i = P.Members.Num() - 1; i >= 0; --i)
	{
		if (!P.Members[i].IsValid() || !P.Members[i]->IsAlive()) { P.Members.RemoveAt(i); }
	}
}

void USRPlatoonSubsystem::Step(float Dt)
{
	for (int32 i = 0; i < Platoons.Num(); ++i)
	{
		FSRPlatoon& P = Platoons[i];
		if (!P.bExists) { continue; }
		Prune(P);
		if (P.Members.Num() == 0)
		{
			// Its last troop has fallen: the platoon is struck off and its slot is free again.
			const FString Name = P.Name;
			Disband(i);
			if (USREconomySubsystem* Economy = USREconomySubsystem::Get(this))
			{
				Economy->PushAlert(ESRAlertKind::Info, FText::Format(LOCTEXT("Fallen", "{0} has fallen to the last troop."), FText::FromString(Name)));
			}
			UE_LOG(LogSovereign, Log, TEXT("PLATOON %d '%s' wiped out: disbanded"), i + 1, *Name);
		}
	}
}

void USRPlatoonSubsystem::Detach(ASRUnit* Unit)
{
	if (!Unit) { return; }
	const int32 Old = Unit->GetPlatoon();
	if (Platoons.IsValidIndex(Old)) { Platoons[Old].Members.Remove(Unit); }
	Unit->SetPlatoon(INDEX_NONE);
}

void USRPlatoonSubsystem::Assign(int32 Index, const TArray<ASRUnit*>& Units)
{
	if (Platoons.Num() == 0) { Reset(); }
	if (!Platoons.IsValidIndex(Index)) { return; }
	FSRPlatoon& P = Platoons[Index];
	for (const TWeakObjectPtr<ASRUnit>& M : P.Members) { if (M.IsValid()) { M->SetPlatoon(INDEX_NONE); } }
	P.Members.Reset();
	const bool bWasNew = !P.bExists;
	P.bExists = true;
	Add(Index, Units);
	if (bWasNew || P.Name.IsEmpty()) { P.Name = DefaultName(Index, GetInfo(Index).Kind); }
	UE_LOG(LogSovereign, Log, TEXT("PLATOON %d '%s' formed with %d troops"), Index + 1, *P.Name, P.Members.Num());
}

void USRPlatoonSubsystem::Add(int32 Index, const TArray<ASRUnit*>& Units)
{
	if (Platoons.Num() == 0) { Reset(); }
	if (!Platoons.IsValidIndex(Index)) { return; }
	FSRPlatoon& P = Platoons[Index];
	if (!P.bExists) { P.bExists = true; }
	for (ASRUnit* U : Units)
	{
		if (!U || !U->IsAlive() || U->GetTeam() != ESRTeam::Player) { continue; }
		Detach(U);
		U->SetPlatoon(Index);
		U->SetStance(P.Stance);
		P.Members.AddUnique(U);
	}
	if (P.Name.IsEmpty()) { P.Name = DefaultName(Index, GetInfo(Index).Kind); }
}

void USRPlatoonSubsystem::Disband(int32 Index)
{
	if (!Platoons.IsValidIndex(Index)) { return; }
	FSRPlatoon& P = Platoons[Index];
	for (const TWeakObjectPtr<ASRUnit>& M : P.Members) { if (M.IsValid()) { M->SetPlatoon(INDEX_NONE); } }
	P = FSRPlatoon();
}

void USRPlatoonSubsystem::RenamePlatoon(int32 Index, const FString& Name)
{
	if (Platoons.IsValidIndex(Index) && Platoons[Index].bExists && !Name.IsEmpty()) { Platoons[Index].Name = Name.Left(24); }
}

void USRPlatoonSubsystem::SetFormation(int32 Index, ESRFormationShape Shape)
{
	if (Platoons.IsValidIndex(Index)) { Platoons[Index].Formation = Shape; }
}

void USRPlatoonSubsystem::SetStance(int32 Index, ESRStance Stance)
{
	if (!Platoons.IsValidIndex(Index)) { return; }
	FSRPlatoon& P = Platoons[Index];
	P.Stance = Stance;
	for (const TWeakObjectPtr<ASRUnit>& M : P.Members)
	{
		if (!M.IsValid()) { continue; }
		M->SetStance(Stance);
		// Holding ground starts now, where they stand; the other stances keep their current order.
		if (Stance == ESRStance::HoldGround && !M->IsEngaged()) { M->OrderHold(); }
	}
}

void USRPlatoonSubsystem::CycleFormation(int32 Index)
{
	if (!Platoons.IsValidIndex(Index)) { return; }
	SetFormation(Index, ESRFormationShape((uint8(Platoons[Index].Formation) + 1) % 4));
	Reform(Index);
}

void USRPlatoonSubsystem::Reform(int32 Index)
{
	// The new shape shows at once: whoever is not fighting closes up round the platoon's centre, facing the way it faces.
	USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this);
	if (!Battle || !Platoons.IsValidIndex(Index)) { return; }
	TArray<ASRUnit*> Free;
	FVector2D Centre = FVector2D::ZeroVector, Facing = FVector2D::ZeroVector;
	for (const TWeakObjectPtr<ASRUnit>& M : Platoons[Index].Members)
	{
		if (!M.IsValid() || !M->IsActive() || M->IsEngaged()) { continue; }
		Free.Add(M.Get());
		Centre += M->GetPos2D();
		Facing += M->GetFacingDir();
	}
	if (Free.Num() < 2) { return; }
	Centre /= Free.Num();
	Facing = Facing.GetSafeNormal();
	if (Facing.IsNearlyZero()) { Facing = FVector2D(1.f, 0.f); }
	Battle->ClearPatrol(Free);
	Battle->CommandMove(Free, Centre, false, Platoons[Index].Formation, true, &Facing);
}

void USRPlatoonSubsystem::CycleStance(int32 Index)
{
	if (!Platoons.IsValidIndex(Index)) { return; }
	SetStance(Index, ESRStance((uint8(Platoons[Index].Stance) + 1) % 3));
}

void USRPlatoonSubsystem::SetRecruitTarget(int32 Index)
{
	for (int32 i = 0; i < Platoons.Num(); ++i) { Platoons[i].bReceivesRecruits = (i == Index) && Platoons[i].bExists; }
}

int32 USRPlatoonSubsystem::GetRecruitTarget() const
{
	for (int32 i = 0; i < Platoons.Num(); ++i) { if (Platoons[i].bExists && Platoons[i].bReceivesRecruits) { return i; } }
	return INDEX_NONE;
}

void USRPlatoonSubsystem::GetMembers(int32 Index, TArray<ASRUnit*>& Out) const
{
	Out.Reset();
	if (!Platoons.IsValidIndex(Index)) { return; }
	for (const TWeakObjectPtr<ASRUnit>& M : Platoons[Index].Members)
	{
		if (M.IsValid() && M->IsActive()) { Out.Add(M.Get()); }
	}
}

FSRPlatoonInfo USRPlatoonSubsystem::GetInfo(int32 Index) const
{
	FSRPlatoonInfo I;
	I.Index = Index;
	if (!Platoons.IsValidIndex(Index) || !Platoons[Index].bExists) { return I; }
	const FSRPlatoon& P = Platoons[Index];
	I.bExists = true;
	I.Name = P.Name;
	I.Formation = P.Formation;
	I.Stance = P.Stance;
	I.bReceivesRecruits = P.bReceivesRecruits;
	float HealthSum = 0.f;
	int32 N = 0;
	for (const TWeakObjectPtr<ASRUnit>& M : P.Members)
	{
		if (!M.IsValid() || !M->IsAlive()) { continue; }
		(M->GetUnitType() == ESRUnitType::Archer ? I.Archers : I.Shieldbearers)++;
		HealthSum += M->GetHealthFrac();
		I.Engaged += M->IsEngaged() ? 1 : 0;
		I.Centre += M->GetPos2D();
		++N;
	}
	if (N > 0) { I.Health = HealthSum / N; I.Centre /= N; }
	if (N == 0) { I.Kind = ESRPlatoonKind::Empty; }
	else if (I.Archers <= N / 5) { I.Kind = ESRPlatoonKind::ShieldWall; }
	else if (I.Shieldbearers <= N / 5) { I.Kind = ESRPlatoonKind::ArcherCompany; }
	else { I.Kind = ESRPlatoonKind::MixedHost; }
	return I;
}

int32 USRPlatoonSubsystem::PlatoonOf(const TArray<ASRUnit*>& Units) const
{
	if (Units.Num() == 0) { return INDEX_NONE; }
	const int32 P = Units[0] ? Units[0]->GetPlatoon() : INDEX_NONE;
	if (!Platoons.IsValidIndex(P)) { return INDEX_NONE; }
	for (const ASRUnit* U : Units) { if (!U || U->GetPlatoon() != P) { return INDEX_NONE; } }
	return P;
}

void USRPlatoonSubsystem::OnRecruit(ASRUnit* Unit)
{
	const int32 Index = GetRecruitTarget();
	if (Index == INDEX_NONE || !Unit || Unit->GetTeam() != ESRTeam::Player) { return; }
	Add(Index, { Unit });
	const FSRPlatoonInfo Info = GetInfo(Index);
	if (USRBattleSubsystem* Battle = USRBattleSubsystem::Get(this); Battle && Info.bExists)
	{
		Battle->CommandMove({ Unit }, Info.Centre, false, ESRFormationShape::Line, false);
	}
}

FString USRPlatoonSubsystem::DefaultName(int32 Index, ESRPlatoonKind Kind) const
{
	static const TCHAR* Ordinals[] = { TEXT("1st"), TEXT("2nd"), TEXT("3rd"), TEXT("4th"), TEXT("5th"), TEXT("6th"), TEXT("7th"), TEXT("8th"), TEXT("9th") };
	return FString::Printf(TEXT("%s %s"), Ordinals[FMath::Clamp(Index, 0, 8)], *KindName(Kind).ToString());
}

FText USRPlatoonSubsystem::KindName(ESRPlatoonKind Kind)
{
	switch (Kind)
	{
	case ESRPlatoonKind::ShieldWall: return LOCTEXT("ShieldWall", "Shield Wall");
	case ESRPlatoonKind::ArcherCompany: return LOCTEXT("ArcherCompany", "Archer Company");
	case ESRPlatoonKind::MixedHost: return LOCTEXT("MixedHost", "Mixed Host");
	default: return LOCTEXT("Platoon", "Platoon");
	}
}

FText USRPlatoonSubsystem::FormationName(ESRFormationShape Shape)
{
	switch (Shape)
	{
	case ESRFormationShape::Column: return LOCTEXT("Column", "Column");
	case ESRFormationShape::Wedge: return LOCTEXT("Wedge", "Wedge");
	case ESRFormationShape::Square: return LOCTEXT("Square", "Square");
	default: return LOCTEXT("Line", "Line");
	}
}

FText USRPlatoonSubsystem::StanceName(ESRStance Stance)
{
	switch (Stance)
	{
	case ESRStance::Defensive: return LOCTEXT("Defensive", "Defensive");
	case ESRStance::HoldGround: return LOCTEXT("Hold", "Hold Ground");
	default: return LOCTEXT("Aggressive", "Aggressive");
	}
}

#undef LOCTEXT_NAMESPACE
