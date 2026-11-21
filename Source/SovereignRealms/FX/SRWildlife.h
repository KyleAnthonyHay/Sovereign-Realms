// Copyright Sovereign Realms.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SRWildlife.generated.h"

class UStaticMeshComponent;
class UMaterialInstanceDynamic;

/**
 * The wildlife: herds of red deer (a stag, hinds, a calf or two) living on the open ground away from the kingdoms.
 * They graze, stand, look round and drift from place to place as a herd; when troops come near, the nearest throw
 * their heads up and the whole herd bolts away from them, white scuts up, and settles again once it is left alone.
 * They never enter water, climb a cliff or come near a building, and they keep out of the way of play: no collision,
 * not selectable, nothing to do with pathing. In the fog of war they are hidden like the foe's troops (a bolting herd
 * would otherwise give an army away).
 *
 * Drawn like the workers: one sprite card and one hidden shadow card each, from SourceArt/Characters/deer_*.png and
 * doe_*.png (Tools/blender/char_deer.py; the troops' sheet layout, the blocks re-used: spawn = graze, attack = bolt,
 * hit = the start, death = looking round). Tuned in Sovereign Feel > World > Wildlife. Spawned by the game mode;
 * sr.Wildlife logs where the herds are, sr.Wildlife <herd> sends the camera's eye there in the log for screenshots.
 */
UCLASS(NotPlaceable)
class SOVEREIGNREALMS_API ASRWildlife : public AActor
{
	GENERATED_BODY()

public:
	ASRWildlife();

	virtual void Tick(float DeltaSeconds) override;

	int32 NumAnimals() const { return Animals.Num(); }
	int32 NumHerds() const { return Herds.Num(); }
	FVector2D HerdCentre(int32 Index) const { return Herds.IsValidIndex(Index) ? Herds[Index].Centre : FVector2D::ZeroVector; }
	bool IsHerdAlarmed(int32 Index) const { return Herds.IsValidIndex(Index) && Herds[Index].bAlarmed; }
	int32 NumFleeing() const;

private:
	enum class EState : uint8 { Graze, Stand, Look, Walk, Start, Flee };

	struct FHerd
	{
		FVector2D Centre = FVector2D::ZeroVector;
		float Spread = 600.f;
		float DriftTimer = 30.f;
		float ScanTimer = 0.f;
		bool bAlarmed = false;
		float CalmTime = 0.f;                    // seconds since a troop was last near
		FVector2D Threat = FVector2D::ZeroVector;
	};
	struct FAnimal
	{
		int32 Herd = 0;
		int32 Kind = 0;                          // 0 stag, 1 hind (and the calf: a small hind)
		float Scale = 1.f;
		FVector2D Pos = FVector2D::ZeroVector;
		FVector2D Goal = FVector2D::ZeroVector;
		float Z = 0.f;
		float Yaw = 0.f;
		EState State = EState::Stand;
		float StateTime = 0.f, StateDuration = 1.f;
		float Distance = 0.f;                    // walked or run in this state (drives the frame)
		float Clock = 0.f;
		float Nerve = 1.f;                       // how soon it takes fright, against the herd's flee radius
		float Veer = 0.f;                        // its own line when the herd bolts (degrees)
		int32 Facing = 0, ShadowFacing = 0;
		FVector4 Applied = FVector4(-1.f, -1.f, -1.f, -1.f);
		UStaticMeshComponent* Card = nullptr;
		UStaticMeshComponent* ShadowCard = nullptr;
	};

	bool Init();
	bool GoodGround(const FVector2D& P, bool bRoomy) const;
	bool Step(FAnimal& A, const FVector2D& Dir, float Dist) const;
	void Begin(FAnimal& A, EState NewState);
	void Think(FAnimal& A, FHerd& H, float Dt);
	void Present(FAnimal& A, float Dt);

	UPROPERTY(Transient) TArray<TObjectPtr<UStaticMeshComponent>> Cards;
	UPROPERTY(Transient) TArray<TObjectPtr<UMaterialInstanceDynamic>> Materials;

	TArray<FHerd> Herds;
	TArray<FAnimal> Animals;
	FRandomStream Rng;
	bool bReady = false;
	float RetryTimer = 0.f;
};
