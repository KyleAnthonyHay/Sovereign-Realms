#include "VLAIWorld.h"
#include "SovereignRealms.h"
#include "VLBattle.h"
#include "VLKing.h"
#include "VLGrid.h"
#include "VLSwordsmanCombat.h"
#include "VLArcherCombat.h"
#include "EngineUtils.h"
#include "Engine/World.h"
#include "Engine/TargetPoint.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
	FString TagOf(const AActor* A, const TCHAR* Prefix)
	{
		for (const FName& T : A->Tags)
		{
			const FString S = T.ToString();
			if (S.StartsWith(Prefix))
			{
				return S.Mid(FCString::Strlen(Prefix));
			}
		}
		return FString();
	}

	/** The json's metres (Y mirrored) to the world's cm. */
	FVector FromJson(const TArray<TSharedPtr<FJsonValue>>& P)
	{
		const double X = P.Num() > 0 ? P[0]->AsNumber() : 0.0;
		const double Y = P.Num() > 1 ? P[1]->AsNumber() : 0.0;
		const double Z = P.Num() > 2 ? P[2]->AsNumber() : 0.0;
		return FVector(X * 100.0, -Y * 100.0, Z * 100.0);
	}

	FVector FromJsonUE(const TArray<TSharedPtr<FJsonValue>>& P)
	{
		return FVector(P.Num() > 0 ? P[0]->AsNumber() : 0.0, P.Num() > 1 ? P[1]->AsNumber() : 0.0, P.Num() > 2 ? P[2]->AsNumber() : 0.0);
	}
}

// ------------------------------------------------------------------------------------------------ helpers

namespace VLAI
{
	FVector Snap(const UVLBattle* B, const FVector& P, int32 Ring)
	{
		UVLGrid* Grid = B ? UVLGrid::Get(B->GetWorld()) : nullptr;
		if (!Grid || !Grid->EnsureBuilt())
		{
			return P;
		}
		const int32 N = Grid->NearestNode(FVector(P.X, P.Y, P.Z + 150.f), Ring, Grid->MainRegion());
		return N != INDEX_NONE ? Grid->NodePos(N) : P;
	}

	float RouteLength(const UVLBattle* B, const FVector& From, const FVector& To, TArray<FVector>* OutRoute)
	{
		UVLGrid* Grid = B ? UVLGrid::Get(B->GetWorld()) : nullptr;
		TArray<FVector> Path;
		if (Grid && Grid->EnsureBuilt() && Grid->FindPath(From, To, Path) && Path.Num() > 0)
		{
			float L = 0.f;
			FVector Prev = From;
			for (const FVector& P : Path)
			{
				L += FVector::Dist2D(Prev, P);
				Prev = P;
			}
			if (OutRoute)
			{
				OutRoute->Reset();
				OutRoute->Add(From);
				OutRoute->Append(Path);
			}
			return L;
		}
		if (OutRoute)
		{
			*OutRoute = { From, To };
		}
		return FVector::Dist2D(From, To) * 1.3f;
	}

	FVector HighGround(const UVLBattle* B, const FVector& P, float Radius)
	{
		UVLGrid* Grid = B ? UVLGrid::Get(B->GetWorld()) : nullptr;
		if (!Grid || !Grid->EnsureBuilt())
		{
			return P;
		}
		FVector Best = P;
		float BestScore = 0.f;
		for (int32 Ring = 1; Ring <= 3; ++Ring)
		{
			const float R = Radius * Ring / 3.f;
			for (int32 k = 0; k < 12; ++k)
			{
				const float A = 2.f * PI * k / 12.f + Ring * 0.26f;
				const FVector Q = P + FVector(FMath::Cos(A), FMath::Sin(A), 0.f) * R;
				const int32 N = Grid->NearestNode(FVector(Q.X, Q.Y, P.Z + 450.f), 3, Grid->MainRegion());
				if (N == INDEX_NONE)
				{
					continue;
				}
				const FVector At = Grid->NodePos(N);
				const float Rise = At.Z - P.Z;
				if (Rise < -60.f || Rise > 450.f || FVector::Dist2D(At, Q) > 300.f)
				{
					continue;       // (down a drop, or up something nobody climbs)
				}
				const float Score = Rise - 0.04f * float(FVector::Dist2D(At, P));
				if (Score > BestScore + 40.f)
				{
					BestScore = Score;
					Best = At;
				}
			}
		}
		return Best;
	}

	bool IsFreeVein(const UVLBattle* B, const AActor* A, FVector* OutAt)
	{
		if (!B || !A || VLRules::KindFromName(TagOf(A, TEXT("Name:"))) != EVLBuilding::Mine)
		{
			return false;
		}
		const FVLBuildingState* S = B->FindBuilding(A);
		const bool bFree = S ? (S->bDestroyed && S->Collapse < 0.f) : TagOf(A, TEXT("Team:")).Equals(TEXT("Neutral"), ESearchCase::IgnoreCase);
		if (OutAt)
		{
			*OutAt = S ? S->Rest : A->GetActorLocation();
		}
		return bFree;
	}

	void MineActors(const UVLBattle* B, TArray<AActor*>& Out)
	{
		Out.Reset();
		if (!B)
		{
			return;
		}
		if (UVLBattle::UseRegistry())
		{
			for (const TWeakObjectPtr<AActor>& M : B->MineActors())
			{
				if (AActor* A = M.Get())
				{
					Out.Add(A);
				}
			}
			return;
		}
		for (TActorIterator<AActor> It(B->GetWorld()); It; ++It)
		{
			if (VLRules::KindFromName(TagOf(*It, TEXT("Name:"))) == EVLBuilding::Mine)
			{
				Out.Add(*It);
			}
		}
	}

	bool Engaged(AVLKing* U)
	{
		const UVLSwordsmanCombat* S = UVLSwordsmanCombat::For(U, false);
		const UVLArcherCombat* A = UVLArcherCombat::For(U, false);
		return (S && S->IsAttacking()) || (A && A->IsAttacking());
	}

	AActor* FightTarget(AVLKing* U)
	{
		if (const UVLSwordsmanCombat* S = UVLSwordsmanCombat::For(U, false); S && S->IsAttacking())
		{
			return S->GetTarget();
		}
		if (const UVLArcherCombat* A = UVLArcherCombat::For(U, false); A && A->IsAttacking())
		{
			return A->GetTarget();
		}
		return nullptr;
	}

	bool Idle(AVLKing* U)
	{
		return !Engaged(U) && !U->HasOrder();
	}

	const TCHAR* PointName(EVLAIPoint Kind)
	{
		switch (Kind)
		{
		case EVLAIPoint::Crown: return TEXT("crown");
		case EVLAIPoint::Crossing: return TEXT("crossing");
		case EVLAIPoint::Flank: return TEXT("flank bridge");
		case EVLAIPoint::Vein: return TEXT("vein");
		case EVLAIPoint::Middle: return TEXT("middle");
		default: return TEXT("marker");
		}
	}

	const TCHAR* EventName(EVLAIEvent Kind)
	{
		switch (Kind)
		{
		case EVLAIEvent::BuildingHit: return TEXT("building struck");
		case EVLAIEvent::BuildingLost: return TEXT("building lost");
		case EVLAIEvent::Raided: return TEXT("raided");
		case EVLAIEvent::UnitLost: return TEXT("troop lost");
		default: return TEXT("foes at home");
		}
	}
}

// ------------------------------------------------------------------------------------------------ the map

float FVLAIMap::AlongOf(const FVector& P) const
{
	const FVector2D A(Castle[0]), D = FVector2D(Castle[1]) - A;
	const float L2 = float(D.SizeSquared());
	return L2 > 1.f ? float(FVector2D::DotProduct(FVector2D(P) - A, D)) / L2 : 0.5f;
}

float FVLAIMap::OffOf(const FVector& P) const
{
	const FVector2D A(Castle[0]), D = (FVector2D(Castle[1]) - A).GetSafeNormal();
	return D.IsNearlyZero() ? 0.f : FMath::Abs(float(FVector2D::CrossProduct(D, FVector2D(P) - A)));
}

int32 FVLAIMap::Count(EVLAIPoint Kind) const
{
	int32 N = 0;
	for (const FVLAIPoint& P : Points)
	{
		N += P.Kind == Kind ? 1 : 0;
	}
	return N;
}

const FVLAIPoint* FVLAIMap::Best(EVLAIPoint Kind) const
{
	const FVLAIPoint* Best = nullptr;
	for (const FVLAIPoint& P : Points)
	{
		if (P.Kind == Kind && (!Best || P.Value > Best->Value))
		{
			Best = &P;
		}
	}
	return Best;
}

void FVLAIMap::Build(UVLBattle* B)
{
	*this = FVLAIMap();
	UWorld* World = B ? B->GetWorld() : nullptr;
	if (!World)
	{
		return;
	}
	bBuilt = true;
	Source = TEXT("level tags");
	for (int32 t = 0; t < 2; ++t)
	{
		if (const AActor* C = B->GetCastle(t))
		{
			Castle[t] = C->GetActorLocation();
		}
	}
	if (!B->GetCastle(0) && B->GetCastle(1))
	{
		Castle[0] = Castle[1] + FVector(-20000.f, 0.f, 0.f);
	}
	if (!B->GetCastle(1) && B->GetCastle(0))
	{
		Castle[1] = Castle[0] + FVector(20000.f, 0.f, 0.f);
	}
	CastleGap = float(FVector::Dist2D(Castle[0], Castle[1]));
	Middle = VLAI::Snap(B, (Castle[0] + Castle[1]) * 0.5f, 60);

	// ---- the markers: each side's gathering point, the Crown
	TSet<FString> LevelTags;
	FVector CrownAt = FVector::ZeroVector;
	bool bCrown = false;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		for (const FName& Tag : It->Tags)
		{
			const FString S = Tag.ToString();
			for (int32 t = 0; t < 2; ++t)
			{
				if (S == FString::Printf(TEXT("TeamStart:%d"), t) || (!bHasMuster[t] && S == FString::Printf(TEXT("Rally:%d"), t)))
				{
					Muster[t] = It->GetActorLocation();
					bHasMuster[t] = true;
				}
			}
			if (S == TEXT("Crown"))
			{
				CrownAt = It->GetActorLocation();
				bCrown = true;
			}
			if (It->IsA<ATargetPoint>())
			{
				LevelTags.Add(S);
			}
		}
	}

	// ---- the map's json (in the editor): its markers and each side's bridge end, where the level has not got them
	{
		const FString MapName = World->GetMapName();
		FString File = MapName.Contains(TEXT("RealmV3")) ? TEXT("realmv3") : MapName.Contains(TEXT("RealmV2")) ? TEXT("realmv2") : (MapName.Contains(TEXT("Highland")) ? TEXT("highland") : (MapName.Contains(TEXT("Realm")) ? TEXT("realm") : FString()));
		if (File.IsEmpty())
		{
			File = MapName;
			File.RemoveFromStart(World->StreamingLevelsPrefix);
			File.RemoveFromStart(TEXT("L_"));
			File = File.ToLower();
		}
		const FString Path = FPaths::Combine(FPaths::ProjectDir(), TEXT("SourceArt"), File + TEXT(".json"));
		FString Text;
		TSharedPtr<FJsonObject> Json;
		if (!File.IsEmpty() && FPaths::FileExists(Path) && FFileHelper::LoadFileToString(Text, *Path))
		{
			TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
			FJsonSerializer::Deserialize(Reader, Json);
		}
		if (Json.IsValid())
		{
			Source += FString::Printf(TEXT(" + %s.json"), *File);
			const TArray<TSharedPtr<FJsonValue>>* Markers = nullptr;
			if (Json->TryGetArrayField(TEXT("markers"), Markers))
			{
				for (const TSharedPtr<FJsonValue>& M : *Markers)
				{
					const TSharedPtr<FJsonObject> O = M->AsObject();
					const TArray<TSharedPtr<FJsonValue>>* Pos = nullptr;
					FString Tag;
					if (!O.IsValid() || !O->TryGetStringField(TEXT("tag"), Tag) || !O->TryGetArrayField(TEXT("pos"), Pos) || LevelTags.Contains(Tag))
					{
						continue;           // (the level's own marker comes first)
					}
					const FVector At = FromJson(*Pos);
					bool bUsed = false;
					for (int32 t = 0; t < 2; ++t)
					{
						if (!bHasMuster[t] && (Tag == FString::Printf(TEXT("TeamStart:%d"), t) || Tag == FString::Printf(TEXT("Rally:%d"), t)))
						{
							Muster[t] = At;
							bHasMuster[t] = bUsed = true;
						}
					}
					if (Tag == TEXT("Crown") && !bCrown)
					{
						CrownAt = At;
						bCrown = bUsed = true;
					}
					if (!bUsed && !Tag.StartsWith(TEXT("TeamStart")) && !Tag.StartsWith(TEXT("Rally")))
					{
						FVLAIPoint& P = Points.AddDefaulted_GetRef();
						P.Kind = EVLAIPoint::Marker;
						P.Name = Tag;
						P.Pos = VLAI::Snap(B, At);
						P.Value = 0.3f;
					}
				}
			}
			const TSharedPtr<FJsonObject>* Teams = nullptr;
			if (Json->TryGetObjectField(TEXT("teams"), Teams))
			{
				for (int32 t = 0; t < 2; ++t)
				{
					const TSharedPtr<FJsonObject>* Side = nullptr;
					const TSharedPtr<FJsonObject>* End = nullptr;
					const TArray<TSharedPtr<FJsonValue>>* Pos = nullptr;
					if ((*Teams)->TryGetObjectField(FString::FromInt(t), Side) && (*Side)->TryGetObjectField(TEXT("bridge_end"), End) && (*End)->TryGetArrayField(TEXT("pos_ue"), Pos))
					{
						BridgeEnd[t] = VLAI::Snap(B, FromJsonUE(*Pos));
						bHasBridgeEnd[t] = true;
					}
				}
			}
		}
	}
	for (int32 t = 0; t < 2; ++t)
	{
		if (!bHasMuster[t])
		{
			Muster[t] = VLAI::Snap(B, Castle[t] + (Castle[1 - t] - Castle[t]).GetSafeNormal2D() * 1500.f);
		}
	}

	// ---- the Crown
	if (bCrown)
	{
		FVLAIPoint& P = Points.AddDefaulted_GetRef();
		P.Kind = EVLAIPoint::Crown;
		P.Name = TEXT("the Crown");
		P.Pos = VLAI::Snap(B, CrownAt, 12);
		P.Value = 1.f;
	}

	// ---- the neutral gold mines (the Crown's twin lode tagged Rich)
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		FVector At;
		if (!VLAI::IsFreeVein(B, *It, &At) || B->FindBuilding(*It))
		{
			continue;
		}
		FVLAIPoint& P = Points.AddDefaulted_GetRef();
		P.Kind = EVLAIPoint::Vein;
		P.bRich = It->ActorHasTag(TEXT("Rich"));
		P.Name = P.bRich ? TEXT("rich vein") : TEXT("neutral mine");
		P.Pos = VLAI::Snap(B, At, 30);
		P.Actor = *It;
		P.Value = P.bRich ? 0.8f : 0.55f;
		if (bCrown && FVector::Dist2D(At, CrownAt) < 4000.f)
		{
			P.Name = TEXT("the Crown's vein");
			if (FVLAIPoint* Crown = Points.FindByPredicate([](const FVLAIPoint& X) { return X.Kind == EVLAIPoint::Crown; }))
			{
				Crown->bRich = true;
				Crown->Value = 1.2f;
			}
		}
	}

	// ---- the bridges: close ones as one crossing; on the way between the castles a crossing, off to the side a flank
	struct FBridge
	{
		FVector Centre;
		FVector Ends[2];
		AActor* Actor;
	};
	TArray<FBridge> Bridges;
	for (TActorIterator<AActor> It(World); It; ++It)
	{
		if (!It->ActorHasTag(TEXT("Name:Bridge")))
		{
			continue;
		}
		FVector Origin, Extent;
		It->GetActorBounds(true, Origin, Extent);
		const FVector Axis = Extent.X >= Extent.Y ? FVector(Extent.X + 350.f, 0.f, 0.f) : FVector(0.f, Extent.Y + 350.f, 0.f);
		FBridge& Br = Bridges.AddDefaulted_GetRef();
		Br.Centre = FVector(Origin.X, Origin.Y, It->GetActorLocation().Z);
		Br.Actor = *It;
		const FVector E0 = Br.Centre - Axis, E1 = Br.Centre + Axis;
		const bool bSwap = FVector::DistSquared2D(E0, Castle[0]) > FVector::DistSquared2D(E1, Castle[0]);
		Br.Ends[0] = bSwap ? E1 : E0;
		Br.Ends[1] = bSwap ? E0 : E1;
	}
	TArray<bool> Taken;
	Taken.Init(false, Bridges.Num());
	for (int32 i = 0; i < Bridges.Num(); ++i)
	{
		if (Taken[i])
		{
			continue;
		}
		TArray<int32> Group = { i };
		Taken[i] = true;
		for (int32 j = i + 1; j < Bridges.Num(); ++j)
		{
			if (!Taken[j] && FVector::Dist2D(Bridges[i].Centre, Bridges[j].Centre) < 3000.f)
			{
				Group.Add(j);
				Taken[j] = true;
			}
		}
		FVLAIPoint P;
		FVector Sum = FVector::ZeroVector;
		P.End[0] = Bridges[i].Ends[0];
		P.End[1] = Bridges[i].Ends[1];
		for (int32 k : Group)
		{
			Sum += Bridges[k].Centre;
			for (int32 t = 0; t < 2; ++t)
			{
				// the end of the group nearest each castle
				if (FVector::DistSquared2D(Bridges[k].Ends[t], Castle[t]) < FVector::DistSquared2D(P.End[t], Castle[t]))
				{
					P.End[t] = Bridges[k].Ends[t];
				}
			}
		}
		P.Pos = Sum / Group.Num();
		P.Actor = Bridges[i].Actor;
		P.End[0] = VLAI::Snap(B, P.End[0], 20);
		P.End[1] = VLAI::Snap(B, P.End[1], 20);
		P.Off = OffOf(P.Pos);
		P.Along = AlongOf(P.Pos);
		const bool bCrownBridge = bCrown && FVector::Dist2D(P.Pos, CrownAt) < 6500.f;
		P.Kind = (P.Off < CastleGap * 0.24f || bCrownBridge) ? EVLAIPoint::Crossing : EVLAIPoint::Flank;
		P.Name = bCrownBridge ? TEXT("the Crown's bridge") : (P.Kind == EVLAIPoint::Crossing ? TEXT("the crossing") : TEXT("a flank bridge"));
		P.Value = P.Kind == EVLAIPoint::Crossing ? (bCrownBridge ? 0.45f : 0.65f) : 0.3f;
		P.Pos = VLAI::Snap(B, P.Pos, 20);
		Points.Add(P);
	}
	// ---- nothing in the middle: the middle itself
	if (!bCrown && Count(EVLAIPoint::Crossing) == 0 && B->GetCastle(0) && B->GetCastle(1))
	{
		FVLAIPoint& P = Points.AddDefaulted_GetRef();
		P.Kind = EVLAIPoint::Middle;
		P.Name = TEXT("the middle");
		P.Pos = Middle;
		P.Value = 0.4f;
	}
	for (FVLAIPoint& P : Points)
	{
		P.Along = AlongOf(P.Pos);
		P.Off = OffOf(P.Pos);
	}
	UE_LOG(LogSovereignRealms, Log, TEXT("AI map (%s): %s"), *Source, *Describe());
}

FString FVLAIMap::Describe() const
{
	TArray<FString> Parts;
	for (const FVLAIPoint& P : Points)
	{
		Parts.Add(FString::Printf(TEXT("%s [%s %.2f] at (%.0f, %.0f) along %.2f off %.0f m"), *P.Name, VLAI::PointName(P.Kind), P.Value, P.Pos.X, P.Pos.Y, P.Along, P.Off / 100.f));
	}
	return FString::Printf(TEXT("castles %.0f m apart, middle (%.0f, %.0f); %s"), CastleGap / 100.f, Middle.X, Middle.Y, Parts.Num() ? *FString::Join(Parts, TEXT("; ")) : TEXT("no features"));
}

// ------------------------------------------------------------------------------------------------ influence

void FVLInfluence::Init(const FBox2D& Bounds, float InCell)
{
	Cell = FMath::Max(InCell, 200.f);
	Origin = Bounds.Min;
	const FVector2D Size = Bounds.GetSize();
	DimX = FMath::Clamp(FMath::CeilToInt(float(Size.X) / Cell), 1, 200);
	DimY = FMath::Clamp(FMath::CeilToInt(float(Size.Y) / Cell), 1, 200);
	Own.Init(0.f, DimX * DimY);
	Foe.Init(0.f, DimX * DimY);
}

void FVLInfluence::Clear()
{
	for (float& V : Own) { V = 0.f; }
	for (float& V : Foe) { V = 0.f; }
}

FIntPoint FVLInfluence::CellOf(const FVector& P) const
{
	return FIntPoint(FMath::Clamp(FMath::FloorToInt(float(P.X - Origin.X) / Cell), 0, FMath::Max(DimX - 1, 0)),
		FMath::Clamp(FMath::FloorToInt(float(P.Y - Origin.Y) / Cell), 0, FMath::Max(DimY - 1, 0)));
}

void FVLInfluence::Stamp(TArray<float>& Layer, const FVector2D& At, float Power, float Radius)
{
	if (!IsValid() || Power <= 0.f)
	{
		return;
	}
	const int32 R = FMath::CeilToInt(Radius / Cell);
	const FIntPoint C = CellOf(FVector(At, 0.f));
	for (int32 dx = -R; dx <= R; ++dx)
	{
		for (int32 dy = -R; dy <= R; ++dy)
		{
			const int32 X = C.X + dx, Y = C.Y + dy;
			if (X < 0 || Y < 0 || X >= DimX || Y >= DimY)
			{
				continue;
			}
			const FVector2D Mid = Origin + FVector2D(X + 0.5f, Y + 0.5f) * Cell;
			const float W = 1.f - float(FVector2D::Distance(Mid, At)) / FMath::Max(Radius, 1.f);
			if (W > 0.f)
			{
				Layer[Y * DimX + X] += Power * W;
			}
		}
	}
}

float FVLInfluence::Sample(const TArray<float>& Layer, const FVector2D& At) const
{
	if (!IsValid())
	{
		return 0.f;
	}
	const FIntPoint C = CellOf(FVector(At, 0.f));
	return Layer[C.Y * DimX + C.X];
}

float FVLInfluence::MaxIn(const TArray<float>& Layer, const FVector2D& At, float Radius) const
{
	if (!IsValid())
	{
		return 0.f;
	}
	const int32 R = FMath::CeilToInt(Radius / Cell);
	const FIntPoint C = CellOf(FVector(At, 0.f));
	float M = 0.f;
	for (int32 dx = -R; dx <= R; ++dx)
	{
		for (int32 dy = -R; dy <= R; ++dy)
		{
			const int32 X = C.X + dx, Y = C.Y + dy;
			if (X >= 0 && Y >= 0 && X < DimX && Y < DimY)
			{
				M = FMath::Max(M, Layer[Y * DimX + X]);
			}
		}
	}
	return M;
}

float FVLInfluence::RouteRisk(const TArray<FVector>& Route, float Step, float* OutPeak) const
{
	float Sum = 0.f, Peak = 0.f;
	for (int32 i = 1; i < Route.Num(); ++i)
	{
		const FVector2D A(Route[i - 1]), D = FVector2D(Route[i]) - A;
		const float L = float(D.Size());
		const int32 N = FMath::Max(1, FMath::CeilToInt(L / Step));
		for (int32 k = 0; k < N; ++k)
		{
			const float V = Sample(Foe, A + D * (float(k) / N));
			Sum += V * (L / N) / 1000.f;
			Peak = FMath::Max(Peak, V);
		}
	}
	if (OutPeak)
	{
		*OutPeak = Peak;
	}
	return Sum;
}

FString FVLInfluence::Ascii(const TMap<FIntPoint, TCHAR>& Marks) const
{
	FString S;
	for (int32 X = DimX - 1; X >= 0; --X)
	{
		S += TEXT("  ");
		for (int32 Y = 0; Y < DimY; ++Y)
		{
			if (const TCHAR* M = Marks.Find(FIntPoint(X, Y)))
			{
				S.AppendChar(*M);
				continue;
			}
			const float O = Own[Y * DimX + X], F = Foe[Y * DimX + X];
			TCHAR Ch = TEXT('.');
			if (O + F >= 0.25f)
			{
				Ch = F > O * 1.6f ? (F >= 2.f ? TEXT('X') : TEXT('x')) : (O > F * 1.6f ? (O >= 2.f ? TEXT('O') : TEXT('o')) : TEXT('#'));
			}
			S.AppendChar(Ch);
		}
		S += TEXT("\n");
	}
	return S;
}
