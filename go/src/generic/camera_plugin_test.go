// Copyright 2024 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package generic

import (
	"bytes"
	"image"
	"image/color"
	"image/png"
	"strings"
	"testing"

	"go.chromium.org/chromiumos/config/go/test/lab/api/passport"
)

// GenerateImage generates solid color within the given width and height image.
func generateImage(width, height int, pixelColor color.RGBA) []byte {
	img := image.NewRGBA(image.Rect(0, 0, width, height))
	for x := 0; x < width; x++ {
		for y := 0; y < height; y++ {
			img.Set(x, y, pixelColor)
		}
	}

	buff := new(bytes.Buffer)
	// Use png for this rather than jpeg.Encode since it's lossless.
	if err := png.Encode(buff, img); err != nil {
		panic(err)
	}
	return buff.Bytes()
}

func TestGetAveragePixel(t *testing.T) {
	tests := []struct {
		name  string
		pixel color.RGBA
	}{
		{
			name:  "red",
			pixel: color.RGBA{R: 255, A: 255},
		},
		{
			name:  "green",
			pixel: color.RGBA{G: 255, A: 255},
		},
		{
			name:  "blue",
			pixel: color.RGBA{B: 255, A: 255},
		},
		{
			name:  "white",
			pixel: color.RGBA{R: 255, G: 255, B: 255, A: 255},
		},
		{
			name:  "black",
			pixel: color.RGBA{A: 255},
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			image := generateImage(500, 500, test.pixel)
			pixel, _ := getAvgPixelColor(image)
			if uint8(pixel.R) != test.pixel.R {
				t.Errorf("Red does not match, got %v, want %v", pixel.R, test.pixel.R)
			}
			if uint8(pixel.G) != test.pixel.G {
				t.Errorf("Green does not match, got %v, want %v", pixel.G, test.pixel.G)
			}
			if uint8(pixel.B) != test.pixel.B {
				t.Errorf("Blue does not match, got %v, want %v", pixel.B, test.pixel.B)
			}
			if uint8(pixel.A) != test.pixel.A {
				t.Errorf("Alpha does not match, got %v, want %v", pixel.A, test.pixel.A)
			}
		})
	}
}

func TestBuildFFmpegVideoArgs(t *testing.T) {
	tests := []struct {
		name           string
		ports          []string
		serials        []string
		req            *passport.CaptureVideoRequest
		wantSubstrings []string
	}{
		{
			name:    "single camera default size uses mjpeg 640x480",
			ports:   []string{"/dev/video0"},
			serials: []string{"cam0"},
			req: &passport.CaptureVideoRequest{
				DurationSeconds: 5,
			},
			wantSubstrings: []string{
				"-f v4l2 -input_format mjpeg -video_size 640x480 -i /dev/video0",
				"-vf drawtext=text='cam0 (/dev/video0)'",
			},
		},
		{
			name:    "multiple cameras custom 1080p includes mjpeg and xstack",
			ports:   []string{"/dev/video0", "/dev/video2"},
			serials: []string{"cam0", "cam1"},
			req: &passport.CaptureVideoRequest{
				DurationSeconds: 3,
				Width:           1920,
				Height:          1080,
			},
			wantSubstrings: []string{
				"-f v4l2 -input_format mjpeg -video_size 1920x1080 -i /dev/video0",
				"-f v4l2 -input_format mjpeg -video_size 1920x1080 -i /dev/video2",
				"-filter_complex",
				"xstack=inputs=2:layout=0_0|w0_0",
			},
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := strings.Join(buildFFmpegVideoArgs(tc.ports, tc.serials, tc.req), " ")
			for _, want := range tc.wantSubstrings {
				if !strings.Contains(got, want) {
					t.Errorf("buildFFmpegVideoArgs() = %q, missing %q", got, want)
				}
			}
		})
	}
}
