// The launcher: the packaged game's SovereignRealms.exe (in place of the engine's bootstrap that only starts
// SovereignRealms\Binaries\Win64\SovereignRealms.exe). A plain Win32 program, GDI only, no engine: its window is up
// and the runner playable within a few hundred milliseconds of the double click, while it starts the game behind it.
//
// It is the loading screen's runner (Source/SovereignRealms/VLLoadingScreen.cpp: the same King David, ground,
// obstacles, numbers and words; the sprites' cells from VLLoadingArt.inl, the art itself bundled in this exe: the
// SourceArt/UI PNGs and the engine's Roboto, as resources, VLLauncher.rc). Keys are live from the first frame (read
// with GetAsyncKeyState, so they work while the game's window has the focus too).
//
// The hand-over: the game signals the named event below once its title screen is up (VLLoadingScreen.cpp, Finished).
// If King David is the computer's (no key pressed) the launcher goes at once and the title is there; if he is
// being played, "PRESS ENTER TO PLAY" (Enter, Esc) first. The best score goes over through Saved\RunnerBest.txt
// (the game reads it with its own [VLRunner] Best, and writes it).
//
// Built by Tools/windows/build_launcher.ps1 (MSVC, called from package.ps1). Started with arguments that a tool
// passes (-unattended, -VLNoRunner) it only starts the game.

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <dwmapi.h>
#include <wincodec.h>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cwchar>
#include <string>
#include <vector>

typedef int32_t int32;
#include "../../../Source/SovereignRealms/VLLoadingArt.inl"
#include "resource.h"

namespace
{
using namespace VLLoadingArt;

// ---- the runner's numbers: VLLoadingScreen.cpp's (u: the ground's pixels; 640 u across the screen at 1080p)
constexpr float BaseSpeed = 140.f, TopSpeed = 320.f, SpeedGain = 4.5f;
constexpr float JumpSpeed = 365.f, Gravity = 1110.f;
constexpr float DiveGravity = 3.f;
constexpr float JumpBuffer = 0.12f;
constexpr float StumbleSeconds = 1.f;
constexpr float CrowHeight = 56.f, ArrowHeight = 9.f;
constexpr float CrowSpeed = 45.f, ArrowSpeed = 120.f;
constexpr float SimStep = 1.f / 120.f;
const wchar_t* const ReadyEvent = L"Local\\SovereignRealmsTitleReady";
const wchar_t* const WindowClass = L"SovereignRealmsRunner";

float Clampf(float V, float Lo, float Hi) { return V < Lo ? Lo : V > Hi ? Hi : V; }
int Clampi(int V, int Lo, int Hi) { return V < Lo ? Lo : V > Hi ? Hi : V; }
float Roundf(float V) { return std::floor(V + 0.5f); }

uint32_t Hash(uint32_t X)
{
	X ^= X >> 16; X *= 0x7feb352dU; X ^= X >> 15; X *= 0x846ca68bU; X ^= X >> 16;
	return X;
}

/** FRandomStream's generator, near enough: a seeded LCG. */
struct FRandom
{
	uint32_t Seed = 1;
	float FRand() { Seed = Seed * 196314165U + 907633515U; return float(Seed >> 8) / 16777216.f; }
	float Range(float A, float B) { return A + (B - A) * FRand(); }
};

struct FColorB { uint8_t B, G, R, A; };

/** An image from the exe's resources, BGRA, straight alpha. */
struct FImage
{
	int W = 0, H = 0;
	std::vector<FColorB> Px;
};

bool LoadPng(IWICImagingFactory* Factory, int Id, FImage& Out)
{
	HRSRC Res = FindResourceW(nullptr, MAKEINTRESOURCEW(Id), RT_RCDATA);
	if (!Res) { return false; }
	HGLOBAL Data = LoadResource(nullptr, Res);
	const DWORD Size = SizeofResource(nullptr, Res);
	BYTE* Bytes = static_cast<BYTE*>(LockResource(Data));
	IWICStream* Stream = nullptr;
	IWICBitmapDecoder* Decoder = nullptr;
	IWICBitmapFrameDecode* Frame = nullptr;
	IWICFormatConverter* Converter = nullptr;
	bool bOk = SUCCEEDED(Factory->CreateStream(&Stream)) && SUCCEEDED(Stream->InitializeFromMemory(Bytes, Size))
		&& SUCCEEDED(Factory->CreateDecoderFromStream(Stream, nullptr, WICDecodeMetadataCacheOnDemand, &Decoder))
		&& SUCCEEDED(Decoder->GetFrame(0, &Frame)) && SUCCEEDED(Factory->CreateFormatConverter(&Converter))
		&& SUCCEEDED(Converter->Initialize(Frame, GUID_WICPixelFormat32bppBGRA, WICBitmapDitherTypeNone, nullptr, 0.0, WICBitmapPaletteTypeCustom));
	if (bOk)
	{
		UINT W = 0, H = 0;
		Converter->GetSize(&W, &H);
		Out.W = int(W);
		Out.H = int(H);
		Out.Px.resize(size_t(W) * H);
		bOk = SUCCEEDED(Converter->CopyPixels(nullptr, W * 4, W * H * 4, reinterpret_cast<BYTE*>(Out.Px.data())));
	}
	if (Converter) { Converter->Release(); }
	if (Frame) { Frame->Release(); }
	if (Decoder) { Decoder->Release(); }
	if (Stream) { Stream->Release(); }
	return bOk;
}

void AddFont(int Id)
{
	if (HRSRC Res = FindResourceW(nullptr, MAKEINTRESOURCEW(Id), RT_RCDATA))
	{
		DWORD Count = 0;
		AddFontMemResourceEx(LockResource(LoadResource(nullptr, Res)), SizeofResource(nullptr, Res), nullptr, &Count);
	}
}

// ---- the frame: a top-down 32-bit DIB the size of the window, drawn into by hand, the words by GDI
struct FCanvas
{
	int W = 0, H = 0;
	uint32_t* Bits = nullptr;
	HDC Dc = nullptr;
	HBITMAP Bitmap = nullptr;
	HGDIOBJ Old = nullptr;

	void Create(HDC Screen, int InW, int InH)
	{
		W = InW;
		H = InH;
		BITMAPINFO Info = {};
		Info.bmiHeader.biSize = sizeof(BITMAPINFOHEADER);
		Info.bmiHeader.biWidth = W;
		Info.bmiHeader.biHeight = -H;
		Info.bmiHeader.biPlanes = 1;
		Info.bmiHeader.biBitCount = 32;
		Info.bmiHeader.biCompression = BI_RGB;
		Dc = CreateCompatibleDC(Screen);
		Bitmap = CreateDIBSection(Screen, &Info, DIB_RGB_COLORS, reinterpret_cast<void**>(&Bits), nullptr, 0);
		Old = SelectObject(Dc, Bitmap);
		SetBkMode(Dc, TRANSPARENT);
	}

	static uint32_t Pack(int R, int G, int B) { return uint32_t(B) | uint32_t(G) << 8 | uint32_t(R) << 16; }

	/** A box in whole pixels (x, y rounded), blended with Alpha. */
	void Box(float X, float Y, float BW, float BH, int R, int G, int B, float Alpha = 1.f)
	{
		const int X0 = Clampi(int(Roundf(X)), 0, W), Y0 = Clampi(int(Roundf(Y)), 0, H);
		const int X1 = Clampi(int(Roundf(X + BW)), 0, W), Y1 = Clampi(int(Roundf(Y + BH)), 0, H);
		if (Alpha >= 1.f)
		{
			const uint32_t C = Pack(R, G, B);
			for (int y = Y0; y < Y1; ++y)
			{
				uint32_t* Row = Bits + size_t(y) * W;
				for (int x = X0; x < X1; ++x) { Row[x] = C; }
			}
			return;
		}
		const int A = int(Alpha * 256.f);
		for (int y = Y0; y < Y1; ++y)
		{
			uint32_t* Row = Bits + size_t(y) * W;
			for (int x = X0; x < X1; ++x)
			{
				const uint32_t D = Row[x];
				const int DB = D & 255, DG = D >> 8 & 255, DR = D >> 16 & 255;
				Row[x] = Pack(DR + ((R - DR) * A >> 8), DG + ((G - DG) * A >> 8), DB + ((B - DB) * A >> 8));
			}
		}
	}

	/** A cell of a sheet (binary alpha), Scale screen pixels a pixel of it, nearest; tinted. */
	void Sprite(const FImage& Img, int SX, int SY, int SW, int SH, float X, float Y, float Scale, float TR = 1.f, float TG = 1.f, float TB = 1.f)
	{
		const int X0 = int(Roundf(X)), Y0 = int(Roundf(Y));
		const int DW = int(Roundf(SW * Scale)), DH = int(Roundf(SH * Scale));
		for (int dy = 0; dy < DH; ++dy)
		{
			const int y = Y0 + dy;
			if (y < 0 || y >= H) { continue; }
			const int sy = SY + Clampi(int((dy + 0.5f) / Scale), 0, SH - 1);
			uint32_t* Row = Bits + size_t(y) * W;
			for (int dx = 0; dx < DW; ++dx)
			{
				const int x = X0 + dx;
				if (x < 0 || x >= W) { continue; }
				const FColorB& C = Img.Px[size_t(sy) * Img.W + SX + Clampi(int((dx + 0.5f) / Scale), 0, SW - 1)];
				if (C.A >= 128)
				{
					Row[x] = Pack(int(C.R * TR), int(C.G * TG), int(C.B * TB));
				}
			}
		}
	}

	/** An image already at its size, alpha blended (the emblem). */
	void Blend(const FImage& Img, int X0, int Y0)
	{
		for (int y = 0; y < Img.H; ++y)
		{
			if (Y0 + y < 0 || Y0 + y >= H) { continue; }
			uint32_t* Row = Bits + size_t(Y0 + y) * W;
			for (int x = 0; x < Img.W; ++x)
			{
				if (X0 + x < 0 || X0 + x >= W) { continue; }
				const FColorB& C = Img.Px[size_t(y) * Img.W + x];
				if (C.A == 0) { continue; }
				const uint32_t D = Row[X0 + x];
				const int A = C.A, DB = D & 255, DG = D >> 8 & 255, DR = D >> 16 & 255;
				Row[X0 + x] = Pack(DR + ((C.R - DR) * A / 255), DG + ((C.G - DG) * A / 255), DB + ((C.B - DB) * A / 255));
			}
		}
	}
};

/** The emblem at Size x Size: an area average of the 256 px source (premultiplied, so its edge stays clean). */
FImage Resample(const FImage& Src, int Size)
{
	FImage Out;
	Out.W = Out.H = Size;
	Out.Px.resize(size_t(Size) * Size);
	const float K = float(Src.W) / Size;
	for (int y = 0; y < Size; ++y)
	{
		for (int x = 0; x < Size; ++x)
		{
			const int SX0 = int(x * K), SX1 = std::max(SX0 + 1, int((x + 1) * K)), SY0 = int(y * K), SY1 = std::max(SY0 + 1, int((y + 1) * K));
			double R = 0, G = 0, B = 0, A = 0;
			int N = 0;
			for (int sy = SY0; sy < SY1 && sy < Src.H; ++sy)
			{
				for (int sx = SX0; sx < SX1 && sx < Src.W; ++sx)
				{
					const FColorB& C = Src.Px[size_t(sy) * Src.W + sx];
					const double a = C.A / 255.0;
					R += C.R * a; G += C.G * a; B += C.B * a; A += a;
					++N;
				}
			}
			FColorB& O = Out.Px[size_t(y) * Size + x];
			O.A = uint8_t(N ? Roundf(float(A / N * 255.0)) : 0);
			O.R = uint8_t(A > 0 ? Clampf(float(R / A), 0.f, 255.f) : 0);
			O.G = uint8_t(A > 0 ? Clampf(float(G / A), 0.f, 255.f) : 0);
			O.B = uint8_t(A > 0 ? Clampf(float(B / A), 0.f, 255.f) : 0);
		}
	}
	return Out;
}

// ---- the runner: VLLoadingScreen.cpp's SVLLoadingScreen::Advance / Step / Spawn, the keys always live
struct FObstacle
{
	int32 Kind = Rock;
	float X = 0.f, Y = 0.f, Speed = 0.f;
};

struct FRunner
{
	FRandom Random;
	std::vector<FObstacle> Obstacles;
	double LastNow = -1.;
	double Scroll = 0.;
	float RunTime = 0.f, RunPhase = 0.f, Score = 0.f, SpawnIn = 0.f;
	float KingY = 0.f, KingVy = 0.f, JumpAsked = 0.f, Stumble = 0.f;
	int32 Best = 0, Waiting = -1;
	bool bPlayer = false, bDucking = false;
	float KingK = 2.f / 3.f, PropK = 5.f / 6.f;

	float PW(int32 Kind) const { return Props[Kind].W * PropK; }
	float PH(int32 Kind) const { return Props[Kind].H * PropK; }
	int32 Frame() const { return KingY > 0.f ? AirFrame : int32(RunPhase) % RunFrames; }

	void Advance(double Now, int Jumps, bool bDown, float WidthU, float KingX)
	{
		if (LastNow < 0.)
		{
			LastNow = Now;
			SpawnIn = WidthU * 0.45f;
		}
		double Left = std::min(std::max(Now - LastNow, 0.), 0.25);
		LastNow = Now;
		if (Jumps > 0)
		{
			if (!bPlayer)
			{
				bPlayer = true;      // the first key takes him over
				Score = 0.f;
			}
			JumpAsked = JumpBuffer;
		}
		const bool bAuto = !bPlayer;
		while (Left > 0.)
		{
			const float Dt = float(std::min(Left, double(SimStep)));
			Left -= SimStep;
			Step(Dt, bAuto ? false : bDown, bAuto, WidthU, KingX);
		}
	}

	void Step(float Dt, bool bDown, bool bAuto, float WidthU, float KingX)
	{
		RunTime += Dt;
		const float Speed = std::min(BaseSpeed + SpeedGain * RunTime, TopSpeed);
		Scroll += Speed * Dt;
		Score += Speed * Dt * 0.1f;
		RunPhase = std::fmod(RunPhase + Dt * RunFps * std::sqrt(Speed / BaseSpeed), float(RunFrames));
		Stumble = std::max(Stumble - Dt, 0.f);
		JumpAsked = std::max(JumpAsked - Dt, 0.f);

		for (int i = int(Obstacles.size()) - 1; i >= 0; --i)
		{
			FObstacle& O = Obstacles[i];
			O.X -= (Speed + O.Speed) * Dt;
			if (O.X + PW(O.Kind) < -8.f)
			{
				Obstacles.erase(Obstacles.begin() + i);
			}
		}
		SpawnIn -= Speed * Dt;
		if (SpawnIn <= 0.f)
		{
			Spawn(Speed, WidthU);
		}

		bool bDuckNow = bDown;
		if (bAuto)
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

		if (Stumble <= 0.f)
		{
			const FHit& Me = bDucking ? CrouchHit[Frame()] : Hit[Frame()];
			const float Head = Me.Head * KingK;
			for (const FObstacle& O : Obstacles)
			{
				if (O.X + 2.f < KingX + Me.Front * KingK && O.X + PW(O.Kind) - 2.f > KingX - Me.Back * KingK && O.Y + 2.f < KingY + Head && O.Y + PH(O.Kind) - 2.f > KingY + Me.Foot * KingK)
				{
					Stumble = StumbleSeconds;
					if (bPlayer) { Best = std::max(Best, int32(Score)); }
					Score = 0.f;
					RunTime = 0.f;
					break;
				}
			}
		}
		else if (bPlayer)
		{
			Score = 0.f;
		}
		if (bPlayer && int32(Score) > Best)
		{
			Best = int32(Score);
		}
	}

	void Spawn(float Speed, float WidthU)
	{
		FObstacle O;
		O.X = WidthU + 8.f;
		if (Waiting != -1)
		{
			O.Kind = Waiting;
			Waiting = -1;
		}
		else
		{
			const float Roll = Random.FRand();
			O.Kind = Roll < 0.30f ? Rock : Roll < 0.56f ? Barrel : Roll < 0.76f ? Stakes : Roll < 0.89f ? Arrow : CrowA;
		}
		if (O.Kind == Arrow || O.Kind == CrowA)
		{
			O.Speed = O.Kind == Arrow ? ArrowSpeed : CrowSpeed;
			O.Y = O.Kind == Arrow ? ArrowHeight : CrowHeight + Random.Range(0.f, 6.f);
			float Room = 1.e9f;
			for (const FObstacle& Other : Obstacles)
			{
				Room = std::min(Room, O.X - (Other.X + PW(Other.Kind)) - (O.Speed - Other.Speed) * WidthU / (Speed + O.Speed));
			}
			if (Room < Speed * 0.9f)
			{
				Waiting = O.Kind;
				SpawnIn = Speed * 0.9f - Room + 1.f;
				return;
			}
		}
		Obstacles.push_back(O);
		float Width = PW(O.Kind);
		if (O.Kind == Barrel && Random.FRand() < 0.3f)
		{
			FObstacle Second = O;
			Second.X += PW(Barrel) + 1.f;
			Obstacles.push_back(Second);
			Width += PW(Barrel) + 1.f;
		}
		SpawnIn = Width + Speed * Random.Range(0.9f, 2.0f);
	}
};

// ---- the app
struct FApp
{
	HWND Window = nullptr;
	FCanvas Canvas;
	FImage Run, Crouch, PropSheet, EmblemSrc, Emblem;
	bool bArt = false;
	FRunner Runner;
	LARGE_INTEGER Freq = {}, Start = {};
	double ReadyAt = -1.;
	HANDLE Ready = nullptr;
	PROCESS_INFORMATION Game = {};
	DWORD GamePid = 0;
	bool bQuit = false;
	bool KeyWas[256] = {};
	int SavedBest = 0;
	std::wstring BestFile, SettingsIni;
	HFONT Fonts[4] = {};         // bold and regular at the sizes of the frame (rebuilt with it)
	int FontPx[4] = {};

	double Now() const
	{
		LARGE_INTEGER T;
		QueryPerformanceCounter(&T);
		return double(T.QuadPart - Start.QuadPart) / double(Freq.QuadPart);
	}

	HFONT Font(int Slot, int Px, bool bBold)
	{
		if (FontPx[Slot] != Px || !Fonts[Slot])
		{
			if (Fonts[Slot]) { DeleteObject(Fonts[Slot]); }
			Fonts[Slot] = CreateFontW(-Px, 0, 0, 0, bBold ? FW_BOLD : FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, OUT_TT_PRECIS, CLIP_DEFAULT_PRECIS, ANTIALIASED_QUALITY, DEFAULT_PITCH, L"Roboto");
			FontPx[Slot] = Px;
		}
		return Fonts[Slot];
	}

	/** Words at (X, Y: their top), Align 0 left, 1 centred, 2 right; MeasureAs: what is measured for the place. */
	void Text(const wchar_t* String, int Slot, float Px, bool bBold, float X, float Y, int Align, COLORREF Color, const wchar_t* MeasureAs = nullptr)
	{
		SelectObject(Canvas.Dc, Font(Slot, std::max(5, int(Roundf(Px))), bBold));
		SIZE Extent = {};
		const wchar_t* M = MeasureAs ? MeasureAs : String;
		GetTextExtentPoint32W(Canvas.Dc, M, int(wcslen(M)), &Extent);
		SetTextColor(Canvas.Dc, Color);
		TextOutW(Canvas.Dc, int(Roundf(X - Extent.cx * 0.5f * Align)), int(Roundf(Y)), String, int(wcslen(String)));
	}

	bool KeyPressed(int Vk, bool bDown)
	{
		const bool bWas = KeyWas[Vk];
		KeyWas[Vk] = bDown;
		return bDown && !bWas;
	}

	/** The keys, whichever of the two windows (this one, the game's) has the focus. */
	void ReadKeys(int& Jumps, bool& bDown, bool& bEnter, bool& bEscape)
	{
		HWND Fg = GetForegroundWindow();
		DWORD Pid = 0;
		GetWindowThreadProcessId(Fg, &Pid);
		const bool bOurs = Fg == Window || (GamePid && Pid == GamePid);
		auto Held = [&](int Vk) { return bOurs && (GetAsyncKeyState(Vk) & 0x8000) != 0; };
		Jumps = 0;
		for (int Vk : { VK_SPACE, VK_UP, int('W') })
		{
			Jumps += KeyPressed(Vk, Held(Vk)) ? 1 : 0;
		}
		bDown = Held(VK_DOWN) || Held('S');
		bEnter = KeyPressed(VK_RETURN, Held(VK_RETURN));
		bEscape = KeyPressed(VK_ESCAPE, Held(VK_ESCAPE));
	}

	void Frame()
	{
		RECT Client;
		GetClientRect(Window, &Client);
		const int W = Client.right, H = Client.bottom;
		if (W <= 0 || H <= 0) { return; }
		if (Canvas.W != W || Canvas.H != H)
		{
			HDC Screen = GetDC(Window);
			if (Canvas.Dc) { SelectObject(Canvas.Dc, Canvas.Old); DeleteObject(Canvas.Bitmap); DeleteDC(Canvas.Dc); }
			Canvas = FCanvas();
			Canvas.Create(Screen, W, H);
			ReleaseDC(Window, Screen);
			Emblem = FImage();
		}
		GdiFlush();

		const double T = Now();
		int Jumps;
		bool bDown, bEnter, bEscape;
		ReadKeys(Jumps, bDown, bEnter, bEscape);

		// the game's title is up: the hand-over (at once, unless he is being played: then on Enter)
		if (ReadyAt < 0. && Ready && WaitForSingleObject(Ready, 0) == WAIT_OBJECT_0)
		{
			ReadyAt = T;
		}
		if (bEscape || (ReadyAt >= 0. && (!Runner.bPlayer || bEnter)))
		{
			bQuit = true;
			return;
		}

		// the layout: VLLoadingScreen.cpp's OnPaint, in the window's pixels
		const float S = float(Clampi(int(Roundf(H / 360.f)), 1, 8));
		const float KS = float(Clampi(int(Roundf(H / 540.f)), 1, 8));
		const float PS = float(Clampi(int(Roundf(H / 216.f)), 1, 20));
		Runner.KingK = KS / S;
		Runner.PropK = PS * 0.5f / S;
		const float WidthU = W / S;
		const float GroundY = Roundf(H * 0.72f);
		const float KingX = Roundf(std::max(WidthU * 0.25f, 110.f));
		Runner.Advance(T, Jumps, bDown, WidthU, KingX);

		FCanvas& C = Canvas;
		C.Box(0.f, 0.f, float(W), float(H), 11, 18, 32);
		const float BandTop = Roundf(H * 0.30f);
		C.Box(0.f, BandTop, float(W), GroundY - BandTop, 14, 23, 40);
		for (int i = 0; i < 40; ++i)
		{
			const uint32_t Hh = Hash(uint32_t(i) * 2654435761u + 17u);
			const float X = std::floor(float(Hh & 1023u) / 1023.f * WidthU * 0.5f) * 2.f * S;
			const float Y = BandTop + std::floor(float(Hh >> 10 & 255u) / 255.f * (GroundY - BandTop - 60.f * S) / (2.f * S)) * 2.f * S;
			const bool bTwinkle = ((Hh >> 20) + uint32_t(T * 1.5)) % 7u == 0;
			C.Box(X, Y, 2.f * S, 2.f * S, 120, 140, 180, bTwinkle ? 0.55f : 0.22f);
		}

		if (bArt && EmblemSrc.W > 0)
		{
			const int E = int(Roundf(H * 0.21f));
			if (Emblem.W != E) { Emblem = Resample(EmblemSrc, E); }
			C.Blend(Emblem, int(Roundf((W - E) * 0.5f)), int(Roundf(H * 0.055f)));
		}

		// the ground
		const float Z = 2.f * S;
		C.Box(0.f, GroundY, float(W), Z, 79, 110, 31);
		C.Box(0.f, GroundY + Z, float(W), Z, 64, 36, 15);
		C.Box(0.f, GroundY + 2.f * Z, float(W), Z, 38, 24, 14);
		{
			const int64_t ScrollU = int64_t(std::floor(Runner.Scroll));
			const int64_t First = ScrollU / 2;
			const float Shift = float(ScrollU % 2) * S;
			for (int i = 0; i <= int(std::ceil(W / Z)) + 1; ++i)
			{
				const uint32_t Hh = Hash(uint32_t(First + i) + 7919u);
				const float X = i * Z - Shift;
				if ((Hh & 7u) == 0) { C.Box(X, GroundY, Z, Z, 107, 143, 46); }
				if ((Hh >> 3 & 15u) == 0) { if (Hh >> 20 & 1u) { C.Box(X, GroundY - Z, Z, Z, 107, 143, 46); } else { C.Box(X, GroundY - Z, Z, Z, 79, 110, 31); } }
				if ((Hh >> 7 & 7u) == 0) { C.Box(X, GroundY + Z, Z, Z, 38, 24, 14); }
				if ((Hh >> 10 & 7u) == 0) { C.Box(X, GroundY + 2.f * Z, Z, Z, 64, 36, 15); }
			}
		}

		if (bArt)
		{
			for (const FObstacle& O : Runner.Obstacles)
			{
				int32 Cell = O.Kind;
				if (Cell == CrowA && std::fmod(T * 6., 2.) >= 1.) { Cell = CrowB; }
				const FProp& P = Props[Cell];
				const float PX = std::floor(O.X * S / (PS * 0.5f)) * PS * 0.5f;
				C.Sprite(PropSheet, int(P.X), 0, int(P.W), int(P.H), PX, GroundY - Roundf(O.Y * S) - P.H * PS * 0.5f, PS * 0.5f);
			}
			const bool bHidden = Runner.Stumble > 0.f && Runner.Stumble < StumbleSeconds - 0.15f && std::fmod(Runner.Stumble, 0.16f) < 0.07f;
			if (!bHidden)
			{
				const bool bRed = Runner.Stumble > StumbleSeconds - 0.15f;
				const FImage& Sheet = Runner.bDucking && Crouch.W > 0 ? Crouch : Run;
				C.Sprite(Sheet, Runner.Frame() * int(CellW), 0, int(CellW), int(CellH), Roundf(KingX * S) - PivotX * KS, GroundY - Roundf(Runner.KingY * S) - PivotY * KS, KS,
					1.f, bRed ? 0.35f : 1.f, bRed ? 0.3f : 1.f);
			}
		}

		// the words (VLStyle's Gold, Parchment, Dim)
		GdiFlush();
		const COLORREF Gold = RGB(219, 168, 66), Parchment = RGB(237, 227, 199), Dim = RGB(153, 156, 158);
		const float Line = std::max(Roundf(H * 0.030f), 10.f);
		const float WordsY = GroundY + Z * 3.f + H * 0.045f;
		const wchar_t* Hint = Runner.bPlayer ? L"Space / Up: jump      Down: duck" : L"Space or Up: take the reins. Jump what is on the ground, duck the crows.";
		if (ReadyAt >= 0.)
		{
			const float Pulse = 0.55f + 0.45f * std::fabs(std::sin(float(T - ReadyAt) * 2.6f));
			const COLORREF Pulsed = RGB(int(11 + (219 - 11) * Pulse), int(18 + (168 - 18) * Pulse), int(32 + (66 - 32) * Pulse));
			Text(L"PRESS ENTER TO PLAY", 0, Line * 1.15f, true, W * 0.5f, WordsY, 1, Pulsed);
		}
		else
		{
			wchar_t Word[16];
			swprintf(Word, 16, L"LOADING%.*s", int(T * 2.5) % 4, L"...");
			Text(Word, 0, Line, true, W * 0.5f, WordsY, 1, Gold, L"LOADING");
		}
		Text(Hint, 1, Line * 0.62f, false, W * 0.5f, WordsY + Line * 1.9f, 1, Dim);
		{
			const float Right = W - H * 0.045f, Top = BandTop + H * 0.022f;
			wchar_t Num[32];
			swprintf(Num, 32, L"%05d", int(Runner.Score));
			Text(Num, 2, Line * 1.1f, true, Right, Top, 2, Runner.bPlayer ? Parchment : Dim);
			if (Runner.Best > 0)
			{
				swprintf(Num, 32, L"BEST %05d", Runner.Best);
				Text(Num, 3, Line * 0.62f, false, Right, Top + Line * 1.5f, 2, Dim);
			}
		}

		HDC Dc = GetDC(Window);
		BitBlt(Dc, 0, 0, W, H, Canvas.Dc, 0, 0, SRCCOPY);
		ReleaseDC(Window, Dc);
	}

	void LoadBest()
	{
		SavedBest = int(GetPrivateProfileIntW(L"VLRunner", L"Best", 0, SettingsIni.c_str()));
		if (FILE* F = _wfopen(BestFile.c_str(), L"rb"))
		{
			int V = 0;
			if (fscanf(F, "%d", &V) == 1) { SavedBest = std::max(SavedBest, V); }
			fclose(F);
		}
		Runner.Best = SavedBest;
	}

	void SaveBest()
	{
		if (Runner.Best > SavedBest)
		{
			if (FILE* F = _wfopen(BestFile.c_str(), L"wb"))
			{
				fprintf(F, "%d\n", Runner.Best);
				fclose(F);
			}
		}
	}

	/** The game's window, to hand the focus to. */
	HWND GameWindow() const
	{
		struct FFind { DWORD Pid; HWND Found; } Find = { GamePid, nullptr };
		EnumWindows([](HWND Hw, LPARAM L) -> BOOL
		{
			FFind* F = reinterpret_cast<FFind*>(L);
			DWORD Pid = 0;
			GetWindowThreadProcessId(Hw, &Pid);
			if (Pid == F->Pid && IsWindowVisible(Hw)) { F->Found = Hw; return FALSE; }
			return TRUE;
		}, reinterpret_cast<LPARAM>(&Find));
		return Find.Found;
	}
};

FApp* GApp = nullptr;

LRESULT CALLBACK WndProc(HWND Hw, UINT Msg, WPARAM W, LPARAM L)
{
	switch (Msg)
	{
	case WM_CLOSE: if (GApp) { GApp->bQuit = true; } return 0;
	case WM_ERASEBKGND: return 1;
	case WM_SETCURSOR: if (LOWORD(L) == HTCLIENT) { SetCursor(nullptr); return TRUE; } break;
	case WM_KEYDOWN: case WM_KEYUP: case WM_SYSKEYDOWN: case WM_CHAR: if (W != VK_F4) { return 0; } break;     // (read by GetAsyncKeyState; Alt+F4 still closes)
	}
	return DefWindowProcW(Hw, Msg, W, L);
}

std::wstring Dir(const std::wstring& Path) { return Path.substr(0, Path.find_last_of(L"\\/")); }
bool Exists(const std::wstring& Path) { return GetFileAttributesW(Path.c_str()) != INVALID_FILE_ATTRIBUTES; }

/** What came after the exe's own name on the command line. */
std::wstring Args()
{
	const wchar_t* C = GetCommandLineW();
	if (*C == L'"') { ++C; while (*C && *C != L'"') { ++C; } if (*C) { ++C; } }
	else { while (*C && *C != L' ' && *C != L'\t') { ++C; } }
	while (*C == L' ' || *C == L'\t') { ++C; }
	return C;
}
}

int WINAPI wWinMain(HINSTANCE Instance, HINSTANCE, PWSTR, int)
{
	SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
	wchar_t Self[MAX_PATH];
	GetModuleFileNameW(nullptr, Self, MAX_PATH);
	const std::wstring Root = Dir(Self);
	std::wstring Exe = Root + L"\\SovereignRealms\\Binaries\\Win64\\SovereignRealms-Win64-Shipping.exe";
	if (!Exists(Exe)) { Exe = Root + L"\\SovereignRealms\\Binaries\\Win64\\SovereignRealms.exe"; }
	if (!Exists(Exe))
	{
		MessageBoxW(nullptr, (L"The game is missing: " + Exe).c_str(), L"Sovereign Realms", MB_ICONERROR);
		return 1;
	}
	const std::wstring Extra = Args();
	std::wstring Lower = Extra;
	for (wchar_t& Ch : Lower) { Ch = wchar_t(towlower(Ch)); }
	const bool bRunner = Lower.find(L"-unattended") == std::wstring::npos && Lower.find(L"-vlnorunner") == std::wstring::npos && Lower.find(L"-server") == std::wstring::npos;

	FApp App;
	GApp = &App;
	QueryPerformanceFrequency(&App.Freq);
	QueryPerformanceCounter(&App.Start);
	App.Runner.Random.Seed = uint32_t(App.Start.QuadPart) | 1u;
	App.BestFile = Root + L"\\SovereignRealms\\Saved\\RunnerBest.txt";
	App.SettingsIni = Root + L"\\SovereignRealms\\Saved\\Config\\Windows\\GameUserSettings.ini";

	if (bRunner)
	{
		// the window first (the runner on screen as soon as can be), then the game behind it
		WNDCLASSEXW Class = { sizeof(Class) };
		Class.lpfnWndProc = WndProc;
		Class.hInstance = Instance;
		Class.hIcon = LoadIconW(Instance, MAKEINTRESOURCEW(IDI_APP));
		Class.hIconSm = Class.hIcon;
		Class.lpszClassName = WindowClass;
		RegisterClassExW(&Class);
		HMONITOR Monitor = MonitorFromPoint(POINT{ 0, 0 }, MONITOR_DEFAULTTOPRIMARY);
		MONITORINFO Info = { sizeof(Info) };
		GetMonitorInfoW(Monitor, &Info);
		const RECT& R = Info.rcMonitor;
		App.Window = CreateWindowExW(WS_EX_TOPMOST | WS_EX_APPWINDOW, WindowClass, L"Sovereign Realms", WS_POPUP | WS_VISIBLE, R.left, R.top, R.right - R.left, R.bottom - R.top,
			nullptr, nullptr, Instance, nullptr);
		SetForegroundWindow(App.Window);
		App.LoadBest();
		AddFont(IDR_ROBOTO_BOLD);
		AddFont(IDR_ROBOTO_REGULAR);
		App.Frame();      // (the night-blue, the ground and the words: before the art is even read)

		CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED);
		IWICImagingFactory* Factory = nullptr;
		if (SUCCEEDED(CoCreateInstance(CLSID_WICImagingFactory, nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&Factory))))
		{
			App.bArt = LoadPng(Factory, IDR_KING_RUN, App.Run) && LoadPng(Factory, IDR_RUNNER_PROPS, App.PropSheet);
			LoadPng(Factory, IDR_KING_CROUCH, App.Crouch);
			LoadPng(Factory, IDR_EMBLEM, App.EmblemSrc);
			Factory->Release();
		}
		App.Ready = CreateEventW(nullptr, TRUE, FALSE, ReadyEvent);
	}

	std::wstring Command = L"\"" + Exe + L"\" SovereignRealms";
	if (!Extra.empty()) { Command += L" " + Extra; }
	STARTUPINFOW Startup = { sizeof(Startup) };
	std::vector<wchar_t> Buffer(Command.begin(), Command.end());
	Buffer.push_back(0);
	if (!CreateProcessW(Exe.c_str(), Buffer.data(), nullptr, nullptr, FALSE, 0, nullptr, (Root + L"\\SovereignRealms\\Binaries\\Win64").c_str(), &Startup, &App.Game))
	{
		MessageBoxW(App.Window, L"The game could not be started.", L"Sovereign Realms", MB_ICONERROR);
		return 1;
	}
	App.GamePid = App.Game.dwProcessId;
	if (!bRunner)
	{
		// (as the engine's bootstrap: wait for the game and pass on its exit code)
		WaitForSingleObject(App.Game.hProcess, INFINITE);
		DWORD Code = 0;
		GetExitCodeProcess(App.Game.hProcess, &Code);
		return int(Code);
	}

	while (!App.bQuit)
	{
		MSG Msg;
		while (PeekMessageW(&Msg, nullptr, 0, 0, PM_REMOVE))
		{
			TranslateMessage(&Msg);
			DispatchMessageW(&Msg);
		}
		if (WaitForSingleObject(App.Game.hProcess, 0) == WAIT_OBJECT_0)
		{
			break;      // (the game is gone: so is this)
		}
		// (no word from the game in two minutes, with its window up: an older build, or no loading screen; hand over)
		if (App.Now() > 120. && App.ReadyAt < 0. && App.GameWindow())
		{
			break;
		}
		App.Frame();
		if (FAILED(DwmFlush()))
		{
			Sleep(8);
		}
	}

	App.SaveBest();
	if (HWND GameWin = App.GameWindow())
	{
		AllowSetForegroundWindow(App.GamePid);
		SetForegroundWindow(GameWin);
	}
	DestroyWindow(App.Window);
	return 0;
}
