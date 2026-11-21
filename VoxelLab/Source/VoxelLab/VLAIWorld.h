#pragma once

#include "CoreMinimal.h"

class UVLBattle;
class AActor;
class AVLKing;

/**
 * The commander's picture of the world (VLEnemyAI.*): the first layer of the AI, under the strategy and the squads.
 *
 *   FVLInfluence   an influence map on 10 m cells over the path grid's ground: each side's fighting strength spread
 *                  round where it stands (troops, the king, towers and castles over their reach), the foe's only as far
 *                  as the commander has seen it (FVLCommander::Seen) plus what it has not seen counted round the foe's
 *                  castle. Queries: what is where, how risky a route is, an ASCII picture for the log (vl.AI)
 *   FVLAIMap       the places worth holding, read from the level and the map's json once a match starts: the Crown
 *                  (a TargetPoint tagged Crown), the crossings and flank bridges (actors tagged Name:Bridge, sorted by
 *                  how far they lie off the line between the castles), the neutral gold mines (Team:Neutral, Rich),
 *                  each side's gathering points (TeamStart:<t>, Rally:<t>), the middle; SourceArt/<map>.json, when it
 *                  is there (the editor, not a packaged game), adds its markers and each side's bridge end. Nothing
 *                  is hard-coded: a sandbox with none of these still has its castles and a middle
 *   FVLAIEvent     what happened lately: its buildings struck or lost, raids on its outlying farms and mines, troops lost
 */
enum class EVLAIPoint : uint8
{
	Crown,          // the mesa in the middle of L_Highlands (its marker)
	Crossing,       // a bridge (or bridges close together) on the way between the castles
	Flank,          // a bridge off to one side: the long way round
	Vein,           // a neutral gold mine: claimed by building a mine on it
	Middle,         // halfway between the castles (when there is nothing better there)
	Marker          // another marker of the map's json
};

struct FVLAIPoint
{
	EVLAIPoint Kind = EVLAIPoint::Middle;
	FString Name;
	FVector Pos = FVector::ZeroVector;      // on the ground (a node of the path grid where there is one)
	float Value = 0.5f;                     // how much holding it is worth
	bool bRich = false;                     // a vein of the Crown's twin lode (tag Rich)
	TWeakObjectPtr<AActor> Actor;           // the bridge's / the mine's actor
	FVector End[2] = { FVector::ZeroVector, FVector::ZeroVector };   // a bridge: the end nearer team 0's / team 1's castle
	float Off = 0.f;                        // cm off the line between the castles (a bridge)
	float Along = 0.5f;                     // 0 at team 0's castle, 1 at team 1's
};

struct FVLAIMap
{
	bool bBuilt = false;
	FString Source;                         // where it was read from ("level tags", "+ highland.json")
	TArray<FVLAIPoint> Points;
	FVector Castle[2] = { FVector::ZeroVector, FVector::ZeroVector };
	FVector Muster[2] = { FVector::ZeroVector, FVector::ZeroVector };   // TeamStart:<t> (else Rally:<t>, else in front of the castle)
	bool bHasMuster[2] = { false, false };
	FVector BridgeEnd[2] = { FVector::ZeroVector, FVector::ZeroVector };    // the json's teams.<t>.bridge_end
	bool bHasBridgeEnd[2] = { false, false };
	FVector Middle = FVector::ZeroVector;
	float CastleGap = 0.f;                  // cm between the castles

	void Build(UVLBattle* B);
	int32 Count(EVLAIPoint Kind) const;
	const FVLAIPoint* Best(EVLAIPoint Kind) const;
	/** 0 at team 0's castle, 1 at team 1's (projected on the line between them). */
	float AlongOf(const FVector& P) const;
	float OffOf(const FVector& P) const;
	FString Describe() const;
};

/** Each side's strength over the map, on Cell cm squares. */
struct FVLInfluence
{
	FVector2D Origin = FVector2D::ZeroVector;
	float Cell = 1000.f;
	int32 DimX = 0, DimY = 0;
	TArray<float> Own, Foe;

	void Init(const FBox2D& Bounds, float InCell);
	bool IsValid() const { return DimX > 0 && DimY > 0; }
	void Clear();
	/** Power spread round At, falling off linearly to nothing at Radius. */
	void Stamp(TArray<float>& Layer, const FVector2D& At, float Power, float Radius);
	float Sample(const TArray<float>& Layer, const FVector2D& At) const;
	float OwnAt(const FVector& At) const { return Sample(Own, FVector2D(At)); }
	float FoeAt(const FVector& At) const { return Sample(Foe, FVector2D(At)); }
	/** The highest value of a layer within Radius of At. */
	float MaxIn(const TArray<float>& Layer, const FVector2D& At, float Radius) const;
	/** The foe's strength summed along a route (one sample every Step cm), and the highest. */
	float RouteRisk(const TArray<FVector>& Route, float Step = 1000.f, float* OutPeak = nullptr) const;
	/** One character a cell, +X up (as the minimap): '.' quiet, 'o' / 'O' ours, 'x' / 'X' the foe's, '#' contested;
	 *  Marks (a cell -> a character) drawn over it. */
	FString Ascii(const TMap<FIntPoint, TCHAR>& Marks) const;
	FIntPoint CellOf(const FVector& P) const;
};

enum class EVLAIEvent : uint8
{
	BuildingHit,    // one of its buildings was struck
	BuildingLost,
	Raided,         // an outlying farm or mine was struck
	UnitLost,
	FoeAtHome       // foes came within its defence radius
};

struct FVLAIEvent
{
	EVLAIEvent Kind = EVLAIEvent::BuildingHit;
	FVector At = FVector::ZeroVector;
	float Time = 0.f;
	float Power = 0.f;
	FString What;
	TWeakObjectPtr<AActor> Actor;
};

namespace VLAI
{
	/** The nearest point of the path grid's main ground to P (P itself without a grid). */
	FVector Snap(const UVLBattle* B, const FVector& P, int32 Ring = 30);
	/** Walking length of the route from A to B over the path grid (cm), and its corners; straight distance x1.3 without one. */
	float RouteLength(const UVLBattle* B, const FVector& From, const FVector& To, TArray<FVector>* OutRoute = nullptr);
	/** The highest standable ground within Radius of P, on P's level or a little up (not down a drop). */
	FVector HighGround(const UVLBattle* B, const FVector& P, float Radius);
	/** A neutral gold mine, or the ruin of a fallen one, a mine can be built on. */
	bool IsFreeVein(const UVLBattle* B, const AActor* Actor, FVector* OutAt = nullptr);
	/** Every actor named as a gold mine (the only ones IsFreeVein can be true of), in the actor walk's order: from the
	 *  battle's cached list (vl.Opt.Registry 0: a walk over every actor). */
	void MineActors(const UVLBattle* B, TArray<AActor*>& Out);
	const TCHAR* PointName(EVLAIPoint Kind);
	/** Fighting now (a swordsman's or an archer's attack under way), and what at. */
	bool Engaged(AVLKing* Unit);
	AActor* FightTarget(AVLKing* Unit);
	/** Neither fighting nor walking an order. */
	bool Idle(AVLKing* Unit);
	const TCHAR* EventName(EVLAIEvent Kind);
}
