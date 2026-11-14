// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Common/SRTypes.h"
#include "SRPlatoonSubsystem.generated.h"

class ASRUnit;

/** What a platoon is, judged from who is in it. */
UENUM(BlueprintType)
enum class ESRPlatoonKind : uint8
{
	Empty,
	ShieldWall,      // all (or nearly all) Shieldbearers
	ArcherCompany,   // all (or nearly all) Archers
	MixedHost,       // both
	Cavalry,         // Horse Riders
	SiegeTrain,      // Catapults
	WorkCrew         // Builders
};

/** One of the player's platoons: a standing group with its own formation and stance (UI: the platoon panel). */
struct FSRPlatoon
{
	bool bExists = false;
	FString Name;
	TArray<TWeakObjectPtr<ASRUnit>> Members;
	ESRFormationShape Formation = ESRFormationShape::Line;
	ESRStance Stance = ESRStance::Aggressive;
	/** New recruits from the castle join this platoon and march to it. */
	bool bReceivesRecruits = false;
};

/** A summary of one platoon for the HUD (computed on demand). */
struct FSRPlatoonInfo
{
	bool bExists = false;
	int32 Index = INDEX_NONE;
	FString Name;
	ESRPlatoonKind Kind = ESRPlatoonKind::Empty;
	ESRFormationShape Formation = ESRFormationShape::Line;
	ESRStance Stance = ESRStance::Aggressive;
	bool bReceivesRecruits = false;
	int32 Shieldbearers = 0;
	int32 Archers = 0;
	int32 Riders = 0;
	int32 Catapults = 0;
	int32 Builders = 0;
	/** Mean health fraction of the living members. */
	float Health = 1.f;
	/** Members fighting right now. */
	int32 Engaged = 0;
	FVector2D Centre = FVector2D::ZeroVector;
};

/**
 * The player's platoons (Sovereign Feel > Platoons > MaxPlatoons, default 6). A unit belongs to at most one.
 *
 *   Ctrl + 1..6     make the selection platoon N (taking its members out of any other platoon)
 *   1..6            select platoon N (twice quickly: centre the camera on it)
 *   Shift + 1..6    add the selection to platoon N
 *   F / G           cycle the selected platoon's formation / stance
 * Moving a platoon uses its formation; its stance is pushed to every member (and to recruits that join it).
 */
UCLASS()
class SOVEREIGNREALMS_API USRPlatoonSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	static USRPlatoonSubsystem* Get(const UObject* WorldContext);
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

	void Reset();
	void Step(float Dt);

	int32 Num() const { return Platoons.Num(); }
	/** Makes platoon Index from these units (replacing its members). */
	void Assign(int32 Index, const TArray<ASRUnit*>& Units);
	void Add(int32 Index, const TArray<ASRUnit*>& Units);
	void Disband(int32 Index);
	void RenamePlatoon(int32 Index, const FString& Name);
	void SetFormation(int32 Index, ESRFormationShape Shape);
	void SetStance(int32 Index, ESRStance Stance);
	void CycleFormation(int32 Index);
	/** Re-forms the platoon where it stands in its current formation. */
	void Reform(int32 Index);
	void CycleStance(int32 Index);
	/** Only one platoon receives recruits at a time; pass INDEX_NONE to stop. */
	void SetRecruitTarget(int32 Index);
	int32 GetRecruitTarget() const;

	void GetMembers(int32 Index, TArray<ASRUnit*>& Out) const;
	FSRPlatoonInfo GetInfo(int32 Index) const;
	const FSRPlatoon* Find(int32 Index) const { return Platoons.IsValidIndex(Index) && Platoons[Index].bExists ? &Platoons[Index] : nullptr; }
	/** The platoon every one of these units belongs to, or INDEX_NONE if they are not exactly one platoon's members. */
	int32 PlatoonOf(const TArray<ASRUnit*>& Units) const;

	/** A fresh recruit left the castle: joins the recruit platoon if there is one (and walks to it). */
	void OnRecruit(ASRUnit* Unit);

	static FText KindName(ESRPlatoonKind Kind);
	/** Each platoon slot's own colour (rings under its troops, its tag over them, its row in the panel). */
	static FLinearColor PlatoonColor(int32 Index);
	static FText FormationName(ESRFormationShape Shape);
	static FText StanceName(ESRStance Stance);

private:
	void Prune(FSRPlatoon& P);
	void Detach(ASRUnit* Unit);
	FString DefaultName(int32 Index, ESRPlatoonKind Kind) const;

	TArray<FSRPlatoon> Platoons;
};
