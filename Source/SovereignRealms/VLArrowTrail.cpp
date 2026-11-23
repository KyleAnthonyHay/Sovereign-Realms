#include "VLArrowTrail.h"
#include "DynamicMeshBuilder.h"
#include "Engine/CollisionProfile.h"
#include "Materials/Material.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialRelevance.h"
#include "Materials/MaterialRenderProxy.h"
#include "PrimitiveSceneProxy.h"
#include "RenderingThread.h"
#include "SceneInterface.h"
#include "SceneView.h"

namespace
{
	/** The streak's head is never thinner on screen than this many pixels (its whole width). */
	constexpr float TrailMinPixels = 1.6f;

	class FVLArrowTrailProxy final : public FPrimitiveSceneProxy
	{
	public:
		FVLArrowTrailProxy(const UVLArrowTrailComponent* Component, UMaterialInterface* InMaterial)
			: FPrimitiveSceneProxy(Component)
			, Material(InMaterial ? InMaterial : UMaterial::GetDefaultMaterial(MD_Surface))
		{
			bWillEverBeLit = false;
			MaterialProxy = Material->GetRenderProxy();
			Relevance = Material->GetRelevance_Concurrent(GetScene().GetShaderPlatform());
		}

		virtual SIZE_T GetTypeHash() const override
		{
			static size_t UniquePointer;
			return reinterpret_cast<size_t>(&UniquePointer);
		}

		void SetTrails_RenderThread(TArray<UVLArrowTrailComponent::FPoint>&& InPoints, int32 InPerTrail, const FVector& InOrigin, float InHalfWidth)
		{
			Points = MoveTemp(InPoints);
			PerTrail = InPerTrail;
			Origin = InOrigin;
			HalfWidth = InHalfWidth;
		}

		virtual void GetDynamicMeshElements(const TArray<const FSceneView*>& Views, const FSceneViewFamily& ViewFamily, uint32 VisibilityMap, FMeshElementCollector& Collector) const override
		{
			if (PerTrail < 2 || Points.Num() < PerTrail || !MaterialProxy)
			{
				return;
			}
			const int32 Trails = Points.Num() / PerTrail;
			for (int32 ViewIndex = 0; ViewIndex < Views.Num(); ++ViewIndex)
			{
				if (!(VisibilityMap & (1 << ViewIndex)))
				{
					continue;
				}
				const FSceneView* View = Views[ViewIndex];
				const FVector3f Eye = FVector3f(View->ViewMatrices.GetViewOrigin() - Origin);
				// cm a pixel covers, per cm of distance from the eye (a perspective view; an orthographic one keeps the ribbon's own width)
				const double ProjX = View->ViewMatrices.GetViewToClip().M[0][0];
				const float ViewWidth = float(View->UnscaledViewRect.Width());
				const float PixelPerDist = View->IsPerspectiveProjection() && ProjX > 1.e-4 && ViewWidth > 1.f ? float(2.0 / (ProjX * ViewWidth)) : 0.f;
				FDynamicMeshBuilder Builder(View->GetFeatureLevel());
				Builder.ReserveVertices(Trails * PerTrail * 2);
				Builder.ReserveTriangles(Trails * (PerTrail - 1) * 2);
				for (int32 t = 0; t < Trails; ++t)
				{
					const UVLArrowTrailComponent::FPoint* P = &Points[t * PerTrail];
					int32 Prev = INDEX_NONE;
					for (int32 i = 0; i < PerTrail; ++i)
					{
						const FVector3f Along = (P[FMath::Min(i + 1, PerTrail - 1)].At - P[FMath::Max(i - 1, 0)].At).GetSafeNormal();
						const FVector3f ToEye = Eye - P[i].At;
						const float Dist = ToEye.Size();
						FVector3f Side = FVector3f::CrossProduct(Along, ToEye).GetSafeNormal();
						if (Side.IsNearlyZero())
						{
							Side = FVector3f::CrossProduct(Along, FVector3f::UpVector).GetSafeNormal(UE_SMALL_NUMBER, FVector3f::RightVector);    // seen end on
						}
						const float Half = P[i].Width * FMath::Max(HalfWidth, Dist * PixelPerDist * TrailMinPixels * 0.5f);
						const float V = float(i) / float(PerTrail - 1);
						const int32 A = Builder.AddVertex(FDynamicMeshVertex(P[i].At - Side * Half, FVector2f(0.f, V), FColor::White));
						Builder.AddVertex(FDynamicMeshVertex(P[i].At + Side * Half, FVector2f(1.f, V), FColor::White));
						if (Prev != INDEX_NONE)
						{
							Builder.AddTriangle(Prev, Prev + 1, A);
							Builder.AddTriangle(Prev + 1, A + 1, A);
						}
						Prev = A;
					}
				}
				FDynamicMeshBuilderSettings Settings;
				Settings.CastShadow = false;
				Settings.bDisableBackfaceCulling = true;
				Settings.bReceivesDecals = false;
				Settings.bUseSelectionOutline = false;
				Builder.GetMesh(FTranslationMatrix(Origin), MaterialProxy, SDPG_World, Settings, nullptr, ViewIndex, Collector);
			}
		}

		virtual FPrimitiveViewRelevance GetViewRelevance(const FSceneView* View) const override
		{
			FPrimitiveViewRelevance Result;
			Result.bDrawRelevance = IsShown(View) && Points.Num() > 0;
			Result.bDynamicRelevance = true;
			Result.bShadowRelevance = false;
			Result.bRenderInMainPass = true;
			Relevance.SetPrimitiveViewRelevance(Result);
			return Result;
		}

		virtual uint32 GetMemoryFootprint() const override { return sizeof(*this) + GetAllocatedSize(); }
		uint32 GetAllocatedSize() const { return FPrimitiveSceneProxy::GetAllocatedSize() + Points.GetAllocatedSize(); }

	private:
		UMaterialInterface* Material = nullptr;         // (kept alive by the component: GetUsedMaterials)
		FMaterialRenderProxy* MaterialProxy = nullptr;
		FMaterialRelevance Relevance;
		TArray<UVLArrowTrailComponent::FPoint> Points;
		int32 PerTrail = 0;
		FVector Origin = FVector::ZeroVector;
		float HalfWidth = 2.f;
	};
}

UVLArrowTrailComponent::UVLArrowTrailComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
	SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);
	SetGenerateOverlapEvents(false);
	SetCastShadow(false);
	bAffectDistanceFieldLighting = false;
	bAffectDynamicIndirectLighting = false;
	bUseAsOccluder = false;
	bReceivesDecals = false;
	SetCanEverAffectNavigation(false);
	Mobility = EComponentMobility::Movable;
}

void UVLArrowTrailComponent::SetTrailMaterial(UMaterialInterface* InMaterial)
{
	if (TrailMaterial != InMaterial)
	{
		TrailMaterial = InMaterial;
		MarkRenderStateDirty();
	}
}

void UVLArrowTrailComponent::GetUsedMaterials(TArray<UMaterialInterface*>& OutMaterials, bool bGetDebugMaterials) const
{
	if (TrailMaterial)
	{
		OutMaterials.Add(TrailMaterial);
	}
}

FPrimitiveSceneProxy* UVLArrowTrailComponent::CreateSceneProxy()
{
	return new FVLArrowTrailProxy(this, TrailMaterial);
}

FBoxSphereBounds UVLArrowTrailComponent::CalcBounds(const FTransform& LocalToWorld) const
{
	return FBoxSphereBounds(Box);
}

void UVLArrowTrailComponent::SetTrails(TArray<FPoint>&& Points, int32 PerTrail, const FVector& Origin, const FBox& WorldBox, float HalfWidth)
{
	const bool bNow = Points.Num() > 0;
	if (!bNow && !bAny)
	{
		return;         // none, as before: nothing to tell the renderer
	}
	bAny = bNow;
	if (bNow)
	{
		Box = WorldBox;
		UpdateBounds();
		MarkRenderTransformDirty();     // (the bounds go to the renderer with the transform)
	}
	if (FVLArrowTrailProxy* Proxy = static_cast<FVLArrowTrailProxy*>(SceneProxy))
	{
		ENQUEUE_RENDER_COMMAND(VLArrowTrails)([Proxy, Moved = MoveTemp(Points), PerTrail, Origin, HalfWidth](FRHICommandListImmediate&) mutable
		{
			Proxy->SetTrails_RenderThread(MoveTemp(Moved), PerTrail, Origin, HalfWidth);
		});
	}
}
