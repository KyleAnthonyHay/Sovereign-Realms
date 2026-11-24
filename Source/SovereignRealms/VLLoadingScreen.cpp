#include "VLLoadingScreen.h"
#include "SovereignRealms.h"
#include "VLHUDStyle.h"
#include "VLLoadingArt.inl"
#include "Engine/Engine.h"
#include "Engine/Texture2D.h"
#include "Engine/TextureRenderTarget2D.h"
#include "Engine/World.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/IInputProcessor.h"
#include "Framework/Application/SlateApplication.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "ImageUtils.h"
#include "Math/RandomStream.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/ConfigCacheIni.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "MoviePlayer.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"
#include "RenderingThread.h"
#include "Slate/WidgetRenderer.h"
#include "Styling/CoreStyle.h"
#include "Styling/SlateBrush.h"
#include "TextureResource.h"
#include "Widgets/SLeafWidget.h"
#include <atomic>

namespace
{
	using namespace VLLoadingArt;

	constexpr float MinimumSeconds = 1.f;   // the screen stays at least this long (a quick load would only flash it)
	constexpr float EnterGrace = 0.35f;     // Enter counts this long after the level is ready (not one pressed during the load)

	// ---- the runner. Lengths in "u", the ground's pixels: 3 screen pixels at 1080p, where the screen is 640 u wide.
	// King David is drawn at a whole number of screen pixels a pixel of his (2 at 1080p: his 128 px cell is 256 px, 2/3 u
	// a pixel, about 74 u of him) and so are the obstacles (5 screen pixels a pixel of theirs at 1080p): OnPaint's KS, PS.
	// Heights above the ground, times in seconds.
	constexpr float BaseSpeed = 140.f, TopSpeed = 320.f, SpeedGain = 4.5f;        // the ground under him: u/s, and what a second adds
	constexpr float JumpSpeed = 365.f, Gravity = 1110.f;                         // 60 u high, 0.66 s in the air
	constexpr float DiveGravity = 3.f;                                           // x, with Down held in the air
	// (ducked, with Down held on the ground, he runs crouched: VLLoadingArt::CrouchHit, T_UI_KingCrouchRun, frame for frame)
	constexpr float JumpBuffer = 0.12f;                                          // a jump pressed this long before landing still counts
	constexpr float StumbleSeconds = 1.f;
	// (what of him can be hit is VLLoadingArt::Hit: his body's silhouette, frame by frame, from the pivot's column)
	constexpr float CrowHeight = 56.f, ArrowHeight = 9.f;                        // a crow flies at his head (under it crouched: 51 u at most), an arrow at his shins (jumped)
	constexpr float CrowSpeed = 45.f, ArrowSpeed = 120.f;                        // on top of the ground's
	constexpr float SimStep = 1.f / 120.f;

	FLinearColor Srgb(uint8 R, uint8 G, uint8 B, float Alpha = 1.f)
	{
		FLinearColor C(FColor(R, G, B));
		C.A = Alpha;
		return C;
	}

	/** The same ground and sky every time: what is on cell X of them. */
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

	/** What the keys (game thread) and the screen (whichever thread paints it) share. */
	struct FVLLoadingShared
	{
		std::atomic<int32> Jumps{ 0 };          // presses of a jump key so far
		std::atomic<bool> bDown{ false };       // Down held
		std::atomic<bool> bLoaded{ false };     // the level is ready: the keys are live
		std::atomic<double> LoadedAt{ 0. };     // FPlatformTime::Seconds() when it was
		std::atomic<int32> Best{ 0 };           // the best score, to save when the screen goes
		double StartedAt = 0.;
		bool bWait = false;                     // stays until Enter (when a match is behind it: see MatchBehind)
	};

	struct FVLLoadingArtSet
	{
		UTexture2D* Run = nullptr;
		UTexture2D* Crouch = nullptr;
		UTexture2D* Props = nullptr;
		UTexture2D* Emblem = nullptr;
	};

	/**
	 * The whole screen, painted in one go: the emblem, the score, King David running over a strip of ground and what
	 * comes at him, "LOADING..." or "PRESS ENTER TO PLAY".
	 *
	 * Nothing here ticks. While the map loads the movie player paints this from its own thread (the game thread is
	 * busy, and reads no keys: he jumps by himself); once the level is ready the game thread paints it from the movie
	 * player's waiting loop, where keys do arrive (FVLLoadingKeys below). So the runner is stepped from OnPaint, by
	 * the clock, and what the keys did comes in through FVLLoadingShared.
	 */
	class SVLLoadingScreen : public SLeafWidget
	{
	public:
		SLATE_BEGIN_ARGS(SVLLoadingScreen) {}
		SLATE_END_ARGS()

		void Construct(const FArguments&, const FVLLoadingArtSet& Art, const TSharedRef<FVLLoadingShared, ESPMode::ThreadSafe>& InShared)
		{
			SetCanTick(false);
			Shared = InShared;
			Best = Shared->Best.load();
			Random.Initialize(int32(FPlatformTime::Cycles64() & 0x7fffffff));
			if (Art.Run)
			{
				for (int32 i = 0; i < RunFrames; ++i)
				{
					Run[i] = Brush(Art.Run, CellW, CellH, float(i) / RunFrames, 0.f, float(i + 1) / RunFrames, 1.f);
				}
				bRun = true;
			}
			for (int32 i = 0; i < RunFrames; ++i)
			{
				// (no crouch-run sheet: he ducks in his run's frames)
				Crouch[i] = Art.Crouch ? Brush(Art.Crouch, CellW, CellH, float(i) / RunFrames, 0.f, float(i + 1) / RunFrames, 1.f) : Run[i];
			}
			if (Art.Props)
			{
				for (int32 i = 0; i < UE_ARRAY_COUNT(Props); ++i)
				{
					const FProp& P = Props[i];
					Prop[i] = Brush(Art.Props, P.W, P.H, P.X / PropsW, 0.f, (P.X + P.W) / PropsW, P.H / PropsH);
				}
				bProps = true;
			}
			if (Art.Emblem)
			{
				Emblem = Brush(Art.Emblem, Art.Emblem->GetSizeX(), Art.Emblem->GetSizeY(), 0.f, 0.f, 1.f, 1.f);
				bEmblem = true;
			}
		}

		/** For the preview (vl.LoadingPreview): the clock is set by hand, and the level is "ready" from LoadedAt on. */
		void SetManualClock(double Now, double LoadedAt, uint32 Seed)
		{
			if (!bManual)
			{
				bManual = true;
				Random.Initialize(int32(Seed));
			}
			ManualNow = Now;
			ManualLoadedAt = LoadedAt;
		}

		virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(1920., 1080.); }

		virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& Geo, const FSlateRect& Culling, FSlateWindowElementList& Out, int32 Layer,
			const FWidgetStyle& InStyle, bool bParentEnabled) const override
		{
			// everything is laid out in the window's own pixels (the sprites must land on whole ones), then handed to
			// Slate in its units
			const float Dpi = FMath::Max(Geo.Scale, 0.01f);
			const FVector2f Size = FVector2f(Geo.GetLocalSize()) * Dpi;
			const FSlateBrush* White = FCoreStyle::Get().GetBrush("WhiteBrush");
			const auto Box = [&](float X, float Y, float W, float H, const FLinearColor& Color, const FSlateBrush* Brush)
			{
				FSlateDrawElement::MakeBox(Out, Layer, Geo.ToPaintGeometry(FVector2f(W, H) / Dpi, FSlateLayoutTransform(FVector2f(X, Y) / Dpi)), Brush, ESlateDrawEffect::None, Color);
			};

			// ---- the clock, and whether the level is ready (the game thread paints only then: see the class comment)
			double Now, LoadedAt;
			bool bLoaded;
			if (bManual)
			{
				Now = ManualNow;
				LoadedAt = ManualLoadedAt;
				bLoaded = Now >= LoadedAt;
			}
			else
			{
				Now = FPlatformTime::Seconds() - Shared->StartedAt;
				if (IsInGameThread() && !Shared->bLoaded.load())
				{
					Shared->LoadedAt.store(FPlatformTime::Seconds());
					Shared->bLoaded.store(true);
					// the level is ready. Only a match waits for Enter: the title screen (the game starting, Main
					// Menu) is let go as soon as its second is up.
					if (Shared->bWait && !MatchBehind())
					{
						Shared->bWait = false;
						if (IGameMoviePlayer* Player = GetMoviePlayer())
						{
							Player->StopMovie();      // (the movie player still keeps it up for MinimumSeconds)
						}
					}
				}
				bLoaded = Shared->bLoaded.load();
				LoadedAt = Shared->LoadedAt.load() - Shared->StartedAt;
			}

			// a pixel of the sprites is a whole number of the screen's: 3 at 1080p. The ground is laid in blocks of two.
			const float S = float(FMath::Clamp(FMath::RoundToInt(Size.Y / 360.f), 1, 8));
			const float KS = float(FMath::Clamp(FMath::RoundToInt(Size.Y / 540.f), 1, 8));        // screen px a pixel of his
			const float PS = float(FMath::Clamp(FMath::RoundToInt(Size.Y / 216.f), 1, 20));       // screen px a pixel of an obstacle's (2 of the sheet's)
			KingK = KS / S;
			PropK = PS * 0.5f / S;
			const float WidthU = Size.X / S;
			const float GroundY = FMath::RoundToFloat(Size.Y * 0.72f);
			const float KingX = FMath::RoundToFloat(FMath::Max(WidthU * 0.25f, 110.f));       // the column of his crown, u from the left

			Advance(Now, bLoaded, WidthU, KingX);

			// ---- the night-blue of the panels, a band a shade lighter behind the run, a few stars
			Box(0.f, 0.f, Size.X, Size.Y, Srgb(11, 18, 32), White);
			++Layer;
			const float BandTop = FMath::RoundToFloat(Size.Y * 0.30f);
			Box(0.f, BandTop, Size.X, GroundY - BandTop, Srgb(14, 23, 40), White);
			++Layer;
			for (int32 i = 0; i < 40; ++i)
			{
				const uint32 H = Hash(uint32(i) * 2654435761u + 17u);
				const float X = FMath::FloorToFloat(float(H & 1023u) / 1023.f * WidthU * 0.5f) * 2.f * S;
				const float Y = BandTop + FMath::FloorToFloat(float(H >> 10 & 255u) / 255.f * (GroundY - BandTop - 60.f * S) / (2.f * S)) * 2.f * S;
				const bool bTwinkle = ((H >> 20) + uint32(Now * 1.5)) % 7u == 0;
				Box(X, Y, 2.f * S, 2.f * S, Srgb(120, 140, 180, bTwinkle ? 0.55f : 0.22f), White);
			}
			++Layer;

			if (bEmblem)
			{
				const float E = FMath::RoundToFloat(Size.Y * 0.21f);
				Box(FMath::RoundToFloat((Size.X - E) * 0.5f), FMath::RoundToFloat(Size.Y * 0.055f), E, E, FLinearColor::White, &Emblem);
			}

			// ---- the ground: a line of turf, earth under it, a tuft or a clod here and there, going by under him
			const FLinearColor Turf = Srgb(79, 110, 31), TurfLit = Srgb(107, 143, 46), Earth = Srgb(64, 36, 15), EarthDark = Srgb(38, 24, 14);
			const float Z = 2.f * S;
			Box(0.f, GroundY, Size.X, Z, Turf, White);
			Box(0.f, GroundY + Z, Size.X, Z, Earth, White);
			Box(0.f, GroundY + 2.f * Z, Size.X, Z, EarthDark, White);
			++Layer;
			{
				const int64 ScrollU = int64(FMath::FloorToDouble(Scroll));
				const int64 First = ScrollU / 2;
				const float Shift = float(ScrollU % 2) * S;
				for (int32 i = 0; i <= FMath::CeilToInt(Size.X / Z) + 1; ++i)
				{
					const uint32 H = Hash(uint32(First + i) + 7919u);
					const float X = i * Z - Shift;
					if ((H & 7u) == 0) { Box(X, GroundY, Z, Z, TurfLit, White); }
					if ((H >> 3 & 15u) == 0) { Box(X, GroundY - Z, Z, Z, (H >> 20 & 1u) ? TurfLit : Turf, White); }      // a tuft
					if ((H >> 7 & 7u) == 0) { Box(X, GroundY + Z, Z, Z, EarthDark, White); }
					if ((H >> 10 & 7u) == 0) { Box(X, GroundY + 2.f * Z, Z, Z, Earth, White); }                          // a clod
				}
			}
			++Layer;

			// ---- what comes at him
			if (bProps)
			{
				for (const FObstacle& O : Obstacles)
				{
					int32 Cell = O.Kind;
					if (Cell == CrowA && FMath::Fmod(Now * 6., 2.) >= 1.) { Cell = CrowB; }       // (its wings)
					const FProp& P = Props[Cell];
					const float PX = FMath::FloorToFloat(O.X * S / (PS * 0.5f)) * PS * 0.5f;          // (on whole half-pixels of theirs)
					Box(PX, GroundY - FMath::RoundToFloat(O.Y * S) - P.H * PS * 0.5f, P.W * PS * 0.5f, P.H * PS * 0.5f, FLinearColor::White, &Prop[Cell]);
				}
			}
			++Layer;

			// ---- King David (a stumble: red for a moment, then blinking until he has his feet again)
			if (bRun)
			{
				const bool bHidden = Stumble > 0.f && Stumble < StumbleSeconds - 0.15f && FMath::Fmod(Stumble, 0.16f) < 0.07f;
				if (!bHidden)
				{
					// the packs' pivot (VLLoadingArt::PivotX, PivotY) on the ground at his column, KS screen pixels a pixel of his
					const FLinearColor Tint = Stumble > StumbleSeconds - 0.15f ? FLinearColor(1.f, 0.35f, 0.3f) : FLinearColor::White;
					// (crouched: the crouch-run's cell of the same frame, so he goes down and up again mid-stride)
					Box(FMath::RoundToFloat(KingX * S) - PivotX * KS, GroundY - FMath::RoundToFloat(KingY * S) - PivotY * KS, CellW * KS, CellH * KS, Tint,
						bDucking ? &Crouch[Frame()] : &Run[Frame()]);
				}
			}
			++Layer;

			// ---- the words, in the interface's face (AVLHUD::Font: Roboto, bold)
			const TSharedRef<FSlateFontMeasure> Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
			const auto Text = [&](const FString& String, float Pixels, float X, float Y, int32 Align, const FLinearColor& Color, const TCHAR* Face, const FString* MeasureAs = nullptr)
			{
				const FSlateFontInfo Font = FCoreStyle::GetDefaultFontStyle(Face, FMath::Max(5.f, Pixels * 0.75f / Dpi));
				const FVector2f Extent = FVector2f(Measure->Measure(MeasureAs ? *MeasureAs : String, Font, Dpi));       // (in screen pixels)
				const FVector2f At(FMath::RoundToFloat(X - Extent.X * 0.5f * Align), FMath::RoundToFloat(Y));
				FSlateDrawElement::MakeText(Out, Layer, Geo.ToPaintGeometry(FVector2f(Extent.X * 1.5f + 8.f, Extent.Y) / Dpi, FSlateLayoutTransform(At / Dpi)),
					String, Font, ESlateDrawEffect::None, Color);
			};
			const FLinearColor Gold(VLStyle::Gold.ToFColor(false)), Parchment(VLStyle::Parchment.ToFColor(false)), Dim(VLStyle::Dim.ToFColor(false));
			const float Line = FMath::Max(FMath::RoundToFloat(Size.Y * 0.030f), 10.f);
			const float WordsY = GroundY + Z * 3.f + Size.Y * 0.045f;
			if (bLoaded && Shared->bWait)
			{
				// (pulsing: it is his to dismiss now)
				const float Pulse = 0.55f + 0.45f * FMath::Abs(FMath::Sin(float(Now - LoadedAt) * 2.6f));
				Text(TEXT("PRESS ENTER TO PLAY"), Line * 1.15f, Size.X * 0.5f, WordsY, 1, Gold.CopyWithNewOpacity(Pulse), TEXT("Bold"));
				Text(bPlayer ? TEXT("Space / Up: jump      Down: duck") : TEXT("Space or Up: take the reins. Jump what is on the ground, duck the crows."),
					Line * 0.62f, Size.X * 0.5f, WordsY + Line * 1.9f, 1, Dim, TEXT("Regular"));
			}
			else
			{
				const FString Word(TEXT("LOADING"));
				Text(Word + FString::ChrN(int32(Now * 2.5) % 4, TEXT('.')), Line, Size.X * 0.5f, WordsY, 1, Gold, TEXT("Bold"), &Word);       // (the word stays put as the dots come)
			}
			{
				const float Right = Size.X - Size.Y * 0.045f, Top = BandTop + Size.Y * 0.022f;
				Text(FString::Printf(TEXT("%05d"), int32(Score)), Line * 1.1f, Right, Top, 2, bPlayer ? Parchment : Dim, TEXT("Bold"));
				if (Best > 0)
				{
					Text(FString::Printf(TEXT("BEST %05d"), Best), Line * 0.62f, Right, Top + Line * 1.5f, 2, Dim, TEXT("Regular"));
				}
			}
			return Layer;
		}

	private:
		struct FObstacle
		{
			int32 Kind = Rock;          // (a crow is CrowA; its other frame is drawn by the clock)
			float X = 0.f, Y = 0.f;     // its cell's left edge (u from the left of the screen), its foot above the ground
			float Speed = 0.f;          // towards him, on top of the ground's
		};

		static FSlateBrush Brush(UTexture2D* Texture, float W, float H, float U0, float V0, float U1, float V1)
		{
			FSlateBrush B;
			B.SetResourceObject(Texture);
			B.ImageSize = FVector2D(W, H);
			B.DrawAs = ESlateBrushDrawType::Image;
			B.SetUVRegion(FBox2f(FVector2f(U0, V0), FVector2f(U1, V1)));
			return B;
		}

		/** Is the world just loaded a match (its URL has Match: New Game, Restart, a saved game loaded)? */
		static bool MatchBehind()
		{
			if (GEngine)
			{
				for (const FWorldContext& Context : GEngine->GetWorldContexts())
				{
					if (Context.WorldType == EWorldType::Game && Context.World())
					{
						return Context.World()->URL.HasOption(TEXT("Match"));
					}
				}
			}
			return false;
		}

		/** An obstacle's size in u (its cell on the sheet, as drawn now). */
		float PW(int32 Kind) const { return Props[Kind].W * PropK; }
		float PH(int32 Kind) const { return Props[Kind].H * PropK; }

		/** The cell of the run he is on: his soles highest in the air. */
		int32 Frame() const
		{
			return KingY > 0.f ? AirFrame : int32(RunPhase) % RunFrames;
		}

		/** Brings the runner up to the clock. (From OnPaint, by one thread at a time: all of this is mutable.) */
		void Advance(double Now, bool bLoaded, float WidthU, float KingX) const
		{
			if (LastNow < 0.)
			{
				LastNow = Now;
				SpawnIn = WidthU * 0.45f;
			}
			// (a long gap is a hitch, or the hand-over from one thread to the other: not played through)
			double Left = FMath::Clamp(Now - LastNow, 0., 0.25);
			LastNow = Now;
			// the keys: the first jump once the level is ready takes him over
			const int32 Jumps = Shared->Jumps.load();
			if (Jumps != SeenJumps)
			{
				SeenJumps = Jumps;
				if (bLoaded && !bManual)
				{
					if (!bPlayer)
					{
						bPlayer = true;
						Score = 0.f;
					}
					JumpAsked = JumpBuffer;
				}
			}
			const bool bDown = bPlayer && Shared->bDown.load();
			while (Left > 0.)
			{
				const float Dt = float(FMath::Min(Left, double(SimStep)));
				Left -= SimStep;
				Step(Dt, bDown, WidthU, KingX);
			}
		}

		void Step(float Dt, bool bDown, float WidthU, float KingX) const
		{
			RunTime += Dt;
			const float Speed = FMath::Min(BaseSpeed + SpeedGain * RunTime, TopSpeed);
			Scroll += Speed * Dt;
			Score += Speed * Dt * 0.1f;
			RunPhase = FMath::Fmod(RunPhase + Dt * RunFps * FMath::Sqrt(Speed / BaseSpeed), float(RunFrames));
			Stumble = FMath::Max(Stumble - Dt, 0.f);
			JumpAsked = FMath::Max(JumpAsked - Dt, 0.f);

			// what comes at him
			for (int32 i = Obstacles.Num() - 1; i >= 0; --i)
			{
				FObstacle& O = Obstacles[i];
				O.X -= (Speed + O.Speed) * Dt;
				if (O.X + PW(O.Kind) < -8.f)
				{
					Obstacles.RemoveAt(i);
				}
			}
			SpawnIn -= Speed * Dt;
			if (SpawnIn <= 0.f)
			{
				Spawn(Speed, WidthU);
			}

			// by himself (while the map loads, and until a key takes over): off the ground when the next thing on it
			// is half a jump away, down while a crow goes over
			bool bDuckNow = bDown;
			if (!bPlayer)
			{
				bDuckNow = false;
				for (const FObstacle& O : Obstacles)
				{
					const float Ahead = O.X + PW(O.Kind) * 0.5f - (KingX - 3.f);
					if (O.Kind == CrowA)
					{
						bDuckNow |= O.X < KingX + 40.f && O.X + PW(O.Kind) > KingX - 35.f;
					}
					else if (KingY <= 0.f && Ahead > -4.f && Ahead <= (Speed + O.Speed) * (JumpSpeed / Gravity) + 2.f)
					{
						JumpAsked = JumpBuffer;
					}
				}
			}

			// the jump (Down on the ground is a duck instead)
			bDucking = bDuckNow && KingY <= 0.f && JumpAsked <= 0.f;
			if (KingY <= 0.f && JumpAsked > 0.f)
			{
				JumpAsked = 0.f;
				KingVy = JumpSpeed;
				KingY = 0.01f;
			}
			if (KingY > 0.f)
			{
				KingVy -= Gravity * (bDuckNow ? DiveGravity : 1.f) * Dt;
				KingY += KingVy * Dt;
				if (KingY <= 0.f)
				{
					KingY = 0.f;
					KingVy = 0.f;
				}
			}

			// run into something: he stumbles, the count starts again, and on he goes
			if (Stumble <= 0.f)
			{
				const FHit& Me = bDucking ? CrouchHit[Frame()] : Hit[Frame()];
				const float Head = Me.Head * KingK;
				for (const FObstacle& O : Obstacles)
				{
					if (O.X + 2.f < KingX + Me.Front * KingK && O.X + PW(O.Kind) - 2.f > KingX - Me.Back * KingK && O.Y + 2.f < KingY + Head && O.Y + PH(O.Kind) - 2.f > KingY + Me.Foot * KingK)
					{
						Stumble = StumbleSeconds;
						if (bPlayer)
						{
							Best = FMath::Max(Best, int32(Score));
							Shared->Best.store(Best);
						}
						Score = 0.f;
						RunTime = 0.f;
						break;
					}
				}
			}
			else if (bPlayer)
			{
				Score = 0.f;        // (nothing counts until he has his feet again)
			}
			if (bPlayer && int32(Score) > Best)
			{
				Best = int32(Score);
				Shared->Best.store(Best);
			}
		}

		void Spawn(float Speed, float WidthU) const
		{
			FObstacle O;
			O.X = WidthU + 8.f;
			// (the preview, vl.LoadingPreview, shows every kind early on: every fourth is a crow, the one after it an arrow)
			if (Waiting != INDEX_NONE)
			{
				O.Kind = Waiting;           // (a flyer that waited for room: below)
				Waiting = INDEX_NONE;
			}
			else
			{
				const float Roll = bManual && Spawned % 4 == 2 ? 0.95f : bManual && Spawned % 4 == 3 ? 0.8f : Random.FRand();
				++Spawned;
				O.Kind = Roll < 0.30f ? Rock : Roll < 0.56f ? Barrel : Roll < 0.76f ? Stakes : Roll < 0.89f ? Arrow : CrowA;
			}
			if (O.Kind == Arrow || O.Kind == CrowA)
			{
				// something that flies catches up with what is on the ground before it: only with room enough that they
				// do not reach him together
				O.Speed = O.Kind == Arrow ? ArrowSpeed : CrowSpeed;
				O.Y = O.Kind == Arrow ? ArrowHeight : CrowHeight + Random.FRandRange(0.f, 6.f);
				float Room = 1.e9f;
				for (const FObstacle& Other : Obstacles)
				{
					Room = FMath::Min(Room, O.X - (Other.X + PW(Other.Kind)) - (O.Speed - Other.Speed) * WidthU / (Speed + O.Speed));
				}
				if (Room < Speed * 0.9f)
				{
					// not yet: it comes once the ground has carried the rest far enough
					Waiting = O.Kind;
					SpawnIn = Speed * 0.9f - Room + 1.f;
					return;
				}
			}
			Obstacles.Add(O);
			float Width = PW(O.Kind);
			if (O.Kind == Barrel && Random.FRand() < 0.3f)         // two barrels side by side
			{
				FObstacle Second = O;
				Second.X += PW(Barrel) + 1.f;
				Obstacles.Add(Second);
				Width += PW(Barrel) + 1.f;
			}
			SpawnIn = Width + Speed * Random.FRandRange(0.9f, 2.0f);
		}

		TSharedPtr<FVLLoadingShared, ESPMode::ThreadSafe> Shared;
		FSlateBrush Run[RunFrames];
		FSlateBrush Crouch[RunFrames];
		FSlateBrush Prop[UE_ARRAY_COUNT(Props)];
		FSlateBrush Emblem;
		bool bRun = false, bProps = false, bEmblem = false;
		bool bManual = false;
		double ManualNow = 0., ManualLoadedAt = 0.;

		// the runner (see Advance)
		mutable FRandomStream Random;
		mutable TArray<FObstacle> Obstacles;
		mutable double LastNow = -1.;
		mutable double Scroll = 0.;
		mutable float RunTime = 0.f, RunPhase = 0.f, Score = 0.f, SpawnIn = 0.f;
		mutable float KingY = 0.f, KingVy = 0.f, JumpAsked = 0.f, Stumble = 0.f;
		mutable int32 SeenJumps = 0, Best = 0, Spawned = 0, Waiting = INDEX_NONE;
		mutable bool bPlayer = false, bDucking = false;
		// u a pixel of his, of the obstacles' sheet (set by OnPaint)
		mutable float KingK = 2.f / 3.f, PropK = 5.f / 6.f;
	};

	FVLLoadingArtSet Art;
	bool bArtLoaded = false;
	FDelegateHandle PrepareHandle, FinishedHandle;
	TSharedPtr<FVLLoadingShared, ESPMode::ThreadSafe> Current;
	TSharedPtr<IInputProcessor> Keys;

	const TCHAR* const BestSection = TEXT("VLRunner");

	void LoadArt()
	{
		if (!bArtLoaded)
		{
			bArtLoaded = true;
			Art.Run = LoadRooted(TEXT("/Game/Voxel/UI/T_UI_KingRun.T_UI_KingRun"));
			Art.Crouch = LoadRooted(TEXT("/Game/Voxel/UI/T_UI_KingCrouchRun.T_UI_KingCrouchRun"));
			Art.Props = LoadRooted(TEXT("/Game/Voxel/UI/T_UI_RunnerProps.T_UI_RunnerProps"));
			Art.Emblem = LoadRooted(TEXT("/Game/Voxel/UI/T_UI_Emblem.T_UI_Emblem"));
		}
	}

	/**
	 * The keys while the screen is up, ahead of everything else Slate would do with them. They arrive only once the
	 * level is ready: a blocking load reads no input at all, and what was pressed meanwhile comes in one burst when
	 * the movie player starts waiting (hence EnterGrace). Enter (A, Start) lets the screen go; Space / Up / W (D-pad
	 * up, X) jumps, Down / S (D-pad down) ducks, or drops him faster in the air.
	 */
	class FVLLoadingKeys : public IInputProcessor
	{
	public:
		virtual void Tick(const float DeltaTime, FSlateApplication& SlateApp, TSharedRef<ICursor> Cursor) override {}
		virtual const TCHAR* GetDebugName() const override { return TEXT("VLLoadingScreen"); }

		virtual bool HandleKeyDownEvent(FSlateApplication& SlateApp, const FKeyEvent& Event) override
		{
			const FKey Key = Event.GetKey();
			if (!Current.IsValid())
			{
				return false;
			}
			if (Key == EKeys::SpaceBar || Key == EKeys::Up || Key == EKeys::W || Key == EKeys::Gamepad_DPad_Up || Key == EKeys::Gamepad_FaceButton_Left)
			{
				if (!Event.IsRepeat())
				{
					++Current->Jumps;
				}
				return true;
			}
			if (Key == EKeys::Down || Key == EKeys::S || Key == EKeys::Gamepad_DPad_Down)
			{
				Current->bDown = true;
				return true;
			}
			if (Key == EKeys::Enter || Key == EKeys::Gamepad_FaceButton_Bottom || Key == EKeys::Gamepad_Special_Right)
			{
				const double Now = FPlatformTime::Seconds();
				if (Current->bWait && Current->bLoaded.load() && !Event.IsRepeat() && Now - Current->LoadedAt.load() >= EnterGrace && Now - Current->StartedAt >= MinimumSeconds)
				{
					if (IGameMoviePlayer* Player = GetMoviePlayer())
					{
						Player->StopMovie();
					}
				}
				return true;
			}
			// every other key is swallowed too: left to the movie player, any key at all would close the screen
			// (FDefaultGameMoviePlayer::OnAnyDown), a key pressed during the load among them
			return true;
		}

		virtual bool HandleMouseButtonDownEvent(FSlateApplication& SlateApp, const FPointerEvent& Event) override
		{
			return Current.IsValid();      // (the same for a click)
		}

		virtual bool HandleKeyUpEvent(FSlateApplication& SlateApp, const FKeyEvent& Event) override
		{
			const FKey Key = Event.GetKey();
			if (Current.IsValid() && (Key == EKeys::Down || Key == EKeys::S || Key == EKeys::Gamepad_DPad_Down))
			{
				Current->bDown = false;
			}
			return false;
		}
	};

	/** The movie player is about to play (a map is about to load) and has nothing to show: this screen. */
	void Prepare()
	{
		IGameMoviePlayer* Player = GetMoviePlayer();
		if (!Player || !FSlateApplication::IsInitialized())
		{
			return;
		}
		LoadArt();
		Current = MakeShared<FVLLoadingShared, ESPMode::ThreadSafe>();
		Current->StartedAt = FPlatformTime::Seconds();
		// Nobody to press Enter in a run a tool drives (the perf and screenshot scripts pass -unattended): there the
		// screen goes when the level is ready, as it did before.
		Current->bWait = !FApp::IsUnattended() && !FParse::Param(FCommandLine::Get(), TEXT("VLNoEnter"));
		int32 Best = 0;
		GConfig->GetInt(BestSection, TEXT("Best"), Best, GGameUserSettingsIni);
		Current->Best = Best;
		if (!Keys.IsValid())
		{
			Keys = MakeShared<FVLLoadingKeys>();
			FSlateApplication::Get().RegisterInputPreProcessor(Keys);
		}

		FLoadingScreenAttributes Screen;
		// Waiting for Enter: the movie player keeps the game thread in its own loop (inside LoadMap, the world not
		// ticking yet) until StopMovie. With a minimum time set, its own "any key or click closes it" stays off.
		Screen.bWaitForManualStop = Current->bWait;
		Screen.bAutoCompleteWhenLoadingCompletes = !Current->bWait;
		Screen.bMoviesAreSkippable = false;
		Screen.bAllowEngineTick = false;
		Screen.MinimumLoadingScreenDisplayTime = MinimumSeconds;
		Screen.WidgetLoadingScreen = SNew(SVLLoadingScreen, Art, Current.ToSharedRef());
		Player->SetupLoadingScreen(Screen);
		UE_LOG(LogSovereignRealms, Log, TEXT("loading screen: up (%s)"), Current->bWait ? TEXT("until Enter") : TEXT("until the level is ready"));
	}

	/** The screen has gone: the keys are the game's again, the best score is kept. */
	void Finished()
	{
		if (Keys.IsValid() && FSlateApplication::IsInitialized())
		{
			FSlateApplication::Get().UnregisterInputPreProcessor(Keys);
		}
		Keys.Reset();
		if (Current.IsValid())
		{
			int32 Saved = 0;
			GConfig->GetInt(BestSection, TEXT("Best"), Saved, GGameUserSettingsIni);
			if (Current->Best.load() > Saved)
			{
				GConfig->SetInt(BestSection, TEXT("Best"), Current->Best.load(), GGameUserSettingsIni);
				GConfig->Flush(false, GGameUserSettingsIni);
			}
			UE_LOG(LogSovereignRealms, Log, TEXT("loading screen: down after %.1f s"), FPlatformTime::Seconds() - Current->StartedAt);
		}
		Current.Reset();
	}

#if !UE_BUILD_SHIPPING
	/**
	 * vl.LoadingPreview [seconds] [ready after] [fps] [seed]: the loading screen as frames, for a film of it. The real
	 * widget, painted off screen at 1920 x 1080 with its clock set by hand (he plays by himself throughout), saved as
	 * Saved/Screenshots/VL/loading_preview/frame_NNNN.png.
	 */
	FAutoConsoleCommand CmdPreview(TEXT("vl.LoadingPreview"), TEXT("vl.LoadingPreview [seconds 18] [ready after 11] [fps 30] [seed 7]: the loading screen as frames in Saved/Screenshots/VL/loading_preview"),
		FConsoleCommandWithArgsDelegate::CreateLambda([](const TArray<FString>& Args)
		{
			const float Seconds = Args.Num() > 0 ? FCString::Atof(*Args[0]) : 18.f;
			const float ReadyAt = Args.Num() > 1 ? FCString::Atof(*Args[1]) : 11.f;
			const int32 Fps = Args.Num() > 2 ? FMath::Clamp(FCString::Atoi(*Args[2]), 1, 120) : 30;
			const uint32 Seed = Args.Num() > 3 ? uint32(FCString::Atoi(*Args[3])) : 7u;
			const FVector2D Size(1920., 1080.);
			LoadArt();
			const TSharedRef<FVLLoadingShared, ESPMode::ThreadSafe> Shared = MakeShared<FVLLoadingShared, ESPMode::ThreadSafe>();
			Shared->bWait = true;
			const TSharedRef<SVLLoadingScreen> Widget = SNew(SVLLoadingScreen, Art, Shared);
			FWidgetRenderer Renderer(true);
			UTextureRenderTarget2D* Target = FWidgetRenderer::CreateTargetFor(Size, TF_Nearest, true);
			Target->AddToRoot();
			const FString Dir = FPaths::ProjectSavedDir() / TEXT("Screenshots/VL/loading_preview");
			IFileManager::Get().DeleteDirectory(*Dir, false, true);
			IFileManager::Get().MakeDirectory(*Dir, true);
			const int32 Frames = FMath::CeilToInt(Seconds * Fps);
			int32 Written = 0;
			for (int32 i = 0; i < Frames; ++i)
			{
				Widget->SetManualClock(double(i) / Fps, ReadyAt, Seed);
				Renderer.DrawWidget(Target, Widget, Size, 1.f / Fps);
				FlushRenderingCommands();
				TArray<FColor> Pixels;
				if (FTextureRenderTargetResource* Resource = Target->GameThread_GetRenderTargetResource(); Resource && Resource->ReadPixels(Pixels))
				{
					// (what comes back is sRGB-encoded once too often: 11 of the background read as 59. Decoded once
					// here, so the frames have the colours the screen shows.)
					for (FColor& C : Pixels)
					{
						C = FLinearColor(C).ToFColor(false);
						C.A = 255;
					}
					TArray64<uint8> Png;
					FImageUtils::PNGCompressImageArray(int32(Size.X), int32(Size.Y), TArrayView64<const FColor>(Pixels.GetData(), Pixels.Num()), Png);
					Written += FFileHelper::SaveArrayToFile(Png, *(Dir / FString::Printf(TEXT("frame_%04d.png"), i))) ? 1 : 0;
				}
			}
			Target->RemoveFromRoot();
			UE_LOG(LogSovereignRealms, Log, TEXT("loading preview: %d of %d frames at %d a second in %s"), Written, Frames, Fps, *Dir);
		}));
#endif
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
		FinishedHandle = Player->OnMoviePlaybackFinished().AddStatic(&Finished);
	}
}

void VLLoadingScreen::Shutdown()
{
	if (PrepareHandle.IsValid() || FinishedHandle.IsValid())
	{
		if (IGameMoviePlayer* Player = GetMoviePlayer())
		{
			Player->OnPrepareLoadingScreen().Remove(PrepareHandle);
			Player->OnMoviePlaybackFinished().Remove(FinishedHandle);
		}
		PrepareHandle.Reset();
		FinishedHandle.Reset();
	}
	Keys.Reset();
	Current.Reset();
}
