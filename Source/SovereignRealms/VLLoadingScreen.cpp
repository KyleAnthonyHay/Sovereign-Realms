#include "VLLoadingScreen.h"
#include "SovereignRealms.h"
#include "VLHUDStyle.h"
#include "Engine/Texture2D.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "MoviePlayer.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/CoreStyle.h"
#include "Styling/SlateBrush.h"
#include "Widgets/SLeafWidget.h"

namespace
{
	// the sheet (king_run_sprite.py: FRAMES, CELL, GROUND, FPS)
	constexpr int32 RunFrames = 8;
	constexpr float CellW = 64.f, CellH = 48.f, SoleRow = 46.f;       // (SoleRow: the row under his soles)
	constexpr float RunFps = 11.f;
	constexpr float RunSpeed = 26.f;        // sprite pixels a second: what his stride covers, so the feet do not slide
	constexpr float MinimumSeconds = 1.f;   // the screen stays at least this long (a quick load would only flash it)

	FLinearColor Srgb(uint8 R, uint8 G, uint8 B)
	{
		return FLinearColor(FColor(R, G, B));
	}

	/** The same ground every time: what stands on cell X of it. */
	uint32 Hash(uint32 X)
	{
		X ^= X >> 16; X *= 0x7feb352dU; X ^= X >> 15; X *= 0x846ca68bU; X ^= X >> 16;
		return X;
	}

	UTexture2D* LoadRooted(const TCHAR* Path)
	{
		UTexture2D* Texture = LoadObject<UTexture2D>(nullptr, Path);
		if (Texture)
		{
			Texture->AddToRoot();       // (the widget's brushes hold it by raw pointer, and are painted off the game thread)
		}
		else
		{
			UE_LOG(LogSovereignRealms, Warning, TEXT("loading screen: %s is missing (Tools/ue/import_loading.py)"), Path);
		}
		return Texture;
	}

	/**
	 * The whole screen, painted in one go. Nothing here ticks: the movie player paints it from its own thread while
	 * the game thread loads, so what is drawn depends on the clock only (FPlatformTime).
	 */
	class SVLLoadingScreen : public SLeafWidget
	{
	public:
		SLATE_BEGIN_ARGS(SVLLoadingScreen) {}
		SLATE_END_ARGS()

		void Construct(const FArguments&, UTexture2D* InRun, UTexture2D* InEmblem)
		{
			SetCanTick(false);
			StartSeconds = FPlatformTime::Seconds();
			if (InRun)
			{
				for (int32 i = 0; i < RunFrames; ++i)
				{
					Run[i].SetResourceObject(InRun);
					Run[i].ImageSize = FVector2D(CellW, CellH);
					Run[i].DrawAs = ESlateBrushDrawType::Image;
					Run[i].SetUVRegion(FBox2f(FVector2f(float(i) / RunFrames, 0.f), FVector2f(float(i + 1) / RunFrames, 1.f)));
				}
				bRun = true;
			}
			if (InEmblem)
			{
				Emblem.SetResourceObject(InEmblem);
				Emblem.ImageSize = FVector2D(InEmblem->GetSizeX(), InEmblem->GetSizeY());
				Emblem.DrawAs = ESlateBrushDrawType::Image;
				bEmblem = true;
			}
		}

		virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(1920., 1080.); }

		virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& Geo, const FSlateRect& Culling, FSlateWindowElementList& Out, int32 Layer,
			const FWidgetStyle& InStyle, bool bParentEnabled) const override
		{
			// everything is laid out in the window's own pixels (the sprite must land on whole ones), then handed to
			// Slate in its units
			const float Dpi = FMath::Max(Geo.Scale, 0.01f);
			const FVector2f Size = FVector2f(Geo.GetLocalSize()) * Dpi;
			const FSlateBrush* White = FCoreStyle::Get().GetBrush("WhiteBrush");
			const double Time = FPlatformTime::Seconds() - StartSeconds;
			const auto Box = [&](float X, float Y, float W, float H, const FLinearColor& Color, const FSlateBrush* Brush)
			{
				FSlateDrawElement::MakeBox(Out, Layer, Geo.ToPaintGeometry(FVector2f(W, H) / Dpi, FSlateLayoutTransform(FVector2f(X, Y) / Dpi)), Brush, ESlateDrawEffect::None, Color);
			};

			// the night-blue of the panels, a band a shade lighter behind the king
			Box(0.f, 0.f, Size.X, Size.Y, Srgb(11, 18, 32), White);
			++Layer;

			// a sprite pixel is a whole number of screen pixels: 6 at 1080p
			const float Z = float(FMath::Clamp(FMath::RoundToInt(Size.Y / 180.f), 2, 14));
			const float GroundY = FMath::RoundToFloat(Size.Y * 0.68f);
			const int32 Cells = FMath::CeilToInt(Size.X / Z);                    // the ground, in sprite pixels: the whole width
			Box(0.f, GroundY - 40.f * Z, Size.X, 40.f * Z, Srgb(14, 23, 40), White);
			++Layer;

			if (bEmblem)
			{
				const float E = FMath::RoundToFloat(Size.Y * 0.27f);
				Box(FMath::RoundToFloat((Size.X - E) * 0.5f), FMath::RoundToFloat(Size.Y * 0.11f), E, E, FLinearColor::White, &Emblem);
			}

			// the ground: a line of turf, earth under it, a tuft or a clod here and there
			const FLinearColor Turf = Srgb(79, 110, 31), TurfLit = Srgb(107, 143, 46), Earth = Srgb(64, 36, 15), EarthDark = Srgb(38, 24, 14);
			Box(0.f, GroundY, Size.X, Z, Turf, White);
			Box(0.f, GroundY + Z, Size.X, Z, Earth, White);
			Box(0.f, GroundY + 2.f * Z, Size.X, Z, EarthDark, White);
			++Layer;
			for (int32 i = 0; i < Cells; ++i)
			{
				const uint32 H = Hash(uint32(i) + 7919u);
				const float X = i * Z;
				if ((H & 7u) == 0) { Box(X, GroundY, Z, Z, TurfLit, White); }
				if ((H >> 3 & 15u) == 0) { Box(X, GroundY - Z, Z, Z, (H >> 20 & 1u) ? TurfLit : Turf, White); }      // a tuft
				if ((H >> 7 & 7u) == 0) { Box(X, GroundY + Z, Z, Z, EarthDark, White); }
				if ((H >> 10 & 7u) == 0) { Box(X, GroundY + 2.f * Z, Z, Z, Earth, White); }                          // a clod
			}
			++Layer;

			// King David: in from the left, across, out at the right, and round again
			if (bRun)
			{
				const float Travel = float(Cells) + CellW;
				const float At = FMath::Fmod(float(Time) * RunSpeed + Travel * 0.36f, Travel) - CellW;
				const int32 Frame = int32(FMath::Fmod(Time * RunFps, double(RunFrames))) % RunFrames;
				Box(FMath::FloorToFloat(At) * Z, GroundY - SoleRow * Z, CellW * Z, CellH * Z, FLinearColor::White, &Run[Frame]);
			}
			++Layer;

			// "LOADING" and its dots, in the interface's face (AVLHUD::Font: Roboto, bold) and gold
			{
				const float Pixels = FMath::Max(FMath::RoundToFloat(Size.Y * 0.030f), 10.f);
				const FSlateFontInfo Font = FCoreStyle::GetDefaultFontStyle("Bold", FMath::Max(5.f, Pixels * 0.75f / Dpi));
				const TSharedRef<FSlateFontMeasure> Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
				const FString Word(TEXT("LOADING"));
				const FVector2f WordSize = FVector2f(Measure->Measure(Word, Font, Dpi));          // (in screen pixels)
				const FString Shown = Word + FString::ChrN(int32(Time * 2.5) % 4, TEXT('.'));    // (the word stays put as the dots come)
				const FVector2f At(FMath::RoundToFloat((Size.X - WordSize.X) * 0.5f), FMath::RoundToFloat(GroundY + Z * 8.f));
				FSlateDrawElement::MakeText(Out, Layer, Geo.ToPaintGeometry(FVector2f(WordSize.X * 1.5f, WordSize.Y) / Dpi, FSlateLayoutTransform(At / Dpi)),
					Shown, Font, ESlateDrawEffect::None, FLinearColor(VLStyle::Gold.ToFColor(false)));
			}
			return Layer;
		}

	private:
		FSlateBrush Run[RunFrames];
		FSlateBrush Emblem;
		bool bRun = false, bEmblem = false;
		double StartSeconds = 0.;
	};

	UTexture2D* RunSheet = nullptr;
	UTexture2D* EmblemArt = nullptr;
	bool bArtLoaded = false;
	FDelegateHandle PrepareHandle;

	/** The movie player is about to play (a map is about to load) and has nothing to show: this screen. */
	void Prepare()
	{
		IGameMoviePlayer* Player = GetMoviePlayer();
		if (!Player || !FSlateApplication::IsInitialized())
		{
			return;
		}
		if (!bArtLoaded)
		{
			bArtLoaded = true;
			RunSheet = LoadRooted(TEXT("/Game/Voxel/UI/T_UI_KingRun.T_UI_KingRun"));
			EmblemArt = LoadRooted(TEXT("/Game/Voxel/UI/T_UI_Emblem.T_UI_Emblem"));
		}
		FLoadingScreenAttributes Screen;
		Screen.bAutoCompleteWhenLoadingCompletes = true;
		Screen.bMoviesAreSkippable = false;
		Screen.bWaitForManualStop = false;
		Screen.bAllowEngineTick = false;
		Screen.MinimumLoadingScreenDisplayTime = MinimumSeconds;
		Screen.WidgetLoadingScreen = SNew(SVLLoadingScreen, RunSheet, EmblemArt);
		Player->SetupLoadingScreen(Screen);
		UE_LOG(LogSovereignRealms, Log, TEXT("loading screen: up"));
	}
}

void VLLoadingScreen::Startup()
{
	// (no movie player in the editor, on a server, in a commandlet: nothing to hook, and Play In Editor loads as before)
	if (!IsMoviePlayerEnabled() || IsRunningDedicatedServer())
	{
		return;
	}
	if (IGameMoviePlayer* Player = GetMoviePlayer())
	{
		// The movie player starts playing at every PreLoadMap; with nothing set up it asks for a screen first. (It
		// forgets the screen after each load, so it asks every time.)
		PrepareHandle = Player->OnPrepareLoadingScreen().AddStatic(&Prepare);
	}
}

void VLLoadingScreen::Shutdown()
{
	if (PrepareHandle.IsValid())
	{
		if (IGameMoviePlayer* Player = GetMoviePlayer())
		{
			Player->OnPrepareLoadingScreen().Remove(PrepareHandle);
		}
		PrepareHandle.Reset();
	}
}
