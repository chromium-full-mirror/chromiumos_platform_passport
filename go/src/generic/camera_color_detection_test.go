// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

package generic

import (
	"fmt"
	"image"
	"image/color"
	"image/jpeg"
	"io"
	"os"
	"path/filepath"
	"testing"

	"github.com/google/go-cmp/cmp"
	"github.com/google/go-cmp/cmp/cmpopts"
)

type testImage struct {
	path          string
	expectedColor string
}

func createTestImages(t *testing.T) []testImage {
	tempDir := t.TempDir()
	createDummyImage(
		filepath.Join(tempDir, "red_hsv.jpg"),
		color.RGBA{R: 255, G: 0, B: 0, A: 255},
	)
	createDummyImage(
		filepath.Join(tempDir, "green_hsv.jpg"),
		color.RGBA{R: 0, G: 255, B: 0, A: 255},
	)
	createDummyImage(
		filepath.Join(tempDir, "blue_hsv.jpg"),
		color.RGBA{R: 0, G: 0, B: 255, A: 255},
	)
	createDummyImage(
		filepath.Join(tempDir, "yellow_hsv.jpg"),
		color.RGBA{R: 255, G: 255, B: 0, A: 255},
	) // Non-target
	createDummyImage(
		filepath.Join(tempDir, "dark_red_hsv.jpg"),
		color.RGBA{R: 100, G: 0, B: 0, A: 255},
	) // Darker red
	createDummyImage(
		filepath.Join(tempDir, "desaturated_red_hsv.jpg"),
		color.RGBA{R: 200, G: 90, B: 90, A: 255},
	) // Desaturated red
	createDummyImage(
		filepath.Join(tempDir, "glare_on_off_screen.jpg"),
		color.RGBA{R: 150, G: 150, B: 150, A: 255},
	) // Grayish-white glare
	createDummyImage(
		filepath.Join(tempDir, "true_black.jpg"),
		color.RGBA{R: 0, G: 0, B: 0, A: 255},
	) // True black

	return []testImage{
		testImage{path: filepath.Join(tempDir, "red_hsv.jpg"), expectedColor: "Red"},
		testImage{path: filepath.Join(tempDir, "green_hsv.jpg"), expectedColor: "Green"},
		testImage{path: filepath.Join(tempDir, "blue_hsv.jpg"), expectedColor: "Blue"},
		testImage{path: filepath.Join(tempDir, "yellow_hsv.jpg"), expectedColor: ""},
		testImage{path: filepath.Join(tempDir, "dark_red_hsv.jpg"), expectedColor: "Off"},
		testImage{path: filepath.Join(tempDir, "desaturated_red_hsv.jpg"), expectedColor: "Red"},
		testImage{path: filepath.Join(tempDir, "glare_on_off_screen.jpg"), expectedColor: "Off"},
		testImage{path: filepath.Join(tempDir, "true_black.jpg"), expectedColor: "Off"},
	}
}

func logHSVAverage(t *testing.T, imagePath string) {
	t.Logf("Analyzing %s (HSV):\n", imagePath)
	file, err := os.Open(imagePath)
	if err != nil {
		t.Fatalf("could not open image file: %v", err)
	}
	defer file.Close()
	img, _, err := image.Decode(file)
	if err != nil {
		t.Fatalf("could not decode image from bytes: %v", err)
	}
	bounds := img.Bounds()
	totalPixels := bounds.Dx() * bounds.Dy()
	if totalPixels == 0 {
		t.Fatalf("image is empty")
	}
	average := HSV{}
	// Iterate through all pixels. For very large images, consider sampling.
	for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
		for x := bounds.Min.X; x < bounds.Max.X; x++ {
			r, g, b, _ := img.At(x, y).RGBA()
			hsv := rgbToHSV(r, g, b)
			average.H += hsv.H / float64(totalPixels)
			average.S += hsv.S / float64(totalPixels)
			average.V += hsv.V / float64(totalPixels)
		}
	}
	t.Logf("Average HSV for %s: HSV: %v\n", imagePath, average)
}

func realTestImages(t *testing.T) []testImage {
	wd, err := os.Getwd()
	testdataDir := filepath.Join(wd, "testdata")
	if err != nil {
		t.Fatalf("Failed to get working directory: %v", err)
	}
	return []testImage{
		testImage{
			path:          filepath.Join(testdataDir, "red_mediocre.jpeg"),
			expectedColor: "Red",
		},
		testImage{
			path:          filepath.Join(testdataDir, "g_false_positive_0.jpeg"),
			expectedColor: "Off",
		},
		testImage{
			path:          filepath.Join(testdataDir, "g_good_0.jpeg"),
			expectedColor: "Green",
		},
		testImage{
			path:          filepath.Join(testdataDir, "g_good_1.jpeg"),
			expectedColor: "Green",
		},
		testImage{
			path:          filepath.Join(testdataDir, "g_good_2.jpeg"),
			expectedColor: "Green",
		},
		testImage{
			path:          filepath.Join(testdataDir, "g_good_3.jpeg"),
			expectedColor: "Green",
		},
		testImage{
			path:          filepath.Join(testdataDir, "g_good_4.jpeg"),
			expectedColor: "Green",
		},
		testImage{
			path:          filepath.Join(testdataDir, "g_good_5.jpeg"),
			expectedColor: "Green",
		},
		testImage{
			path:          filepath.Join(testdataDir, "g_good_6.jpeg"),
			expectedColor: "Green",
		},
		testImage{
			path:          filepath.Join(testdataDir, "g_good_7.jpeg"),
			expectedColor: "Green",
		},
		testImage{
			path:          filepath.Join(testdataDir, "r_good_0.jpeg"),
			expectedColor: "Red",
		},
		testImage{
			path:          filepath.Join(testdataDir, "r_good_1.jpeg"),
			expectedColor: "Red",
		},
		testImage{
			path:          filepath.Join(testdataDir, "r_good_2.jpeg"),
			expectedColor: "Red",
		},
		testImage{
			path:          filepath.Join(testdataDir, "r_borderline_0.jpeg"),
			expectedColor: "",
		},
		testImage{
			path:          filepath.Join(testdataDir, "r_good_4.jpeg"),
			expectedColor: "Red",
		},
		testImage{
			path:          filepath.Join(testdataDir, "r_good_5.jpeg"),
			expectedColor: "Red",
		},
		testImage{
			path:          filepath.Join(testdataDir, "monitor_off_glare_led_reflection.jpeg"),
			expectedColor: "Off",
		},
		testImage{
			path:          filepath.Join(testdataDir, "monitor_off_glare_led_reflection_1.jpeg"),
			expectedColor: "Off",
		},
		testImage{
			path:          filepath.Join(testdataDir, "monitor_off_with_color_reflections.jpeg"),
			expectedColor: "Off",
		},
		testImage{
			path:          filepath.Join(testdataDir, "monitor_off_with_monitor_message_1.jpeg"),
			expectedColor: "Off",
		},
		testImage{
			path:          filepath.Join(testdataDir, "monitor_off_with_monitor_message.jpeg"),
			expectedColor: "Off",
		},
		testImage{
			path:          filepath.Join(testdataDir, "monitor_off_with_extreme_glare.jpeg"),
			expectedColor: "Off",
		},
	}
}

var hsvRanges = map[string]HSVRange{
	// red can be on either end of the hue range so split into two ranges.
	"Red":   HSVRange{Min: HSV{H: 330, S: 0.45, V: 0.55}, Max: HSV{H: 30, S: 1.0, V: 1.0}},
	"Green": HSVRange{Min: HSV{H: 90, S: 0.45, V: 0.55}, Max: HSV{H: 165, S: 1.0, V: 1.0}},
	"Blue":  HSVRange{Min: HSV{H: 210, S: 0.45, V: 0.55}, Max: HSV{H: 270, S: 1.0, V: 1.0}},
	// Off we are just looking at value and ignoring hue and saturation
	"Off": HSVRange{Min: HSV{H: 0, S: 0.0, V: 0.0}, Max: HSV{H: 360, S: 1.0, V: 0.60}},
}

func TestSimpleCheckDisplayColorHSV(t *testing.T) {
	// ensure the color detection works with very simple generated images that
	// have a solid known color.
	testCheckDisplayColorHSV(t, createTestImages(t))
}

func TestRealCheckDisplayColorHSV(t *testing.T) {
	// ensure the color detection works with real images, that were pulled from
	// real PASIT test runs in the lab.  This image set includes images that
	// were problematic in the past.
	testCheckDisplayColorHSV(t, realTestImages(t))
}

func testCheckDisplayColorHSV(t *testing.T, testImages []testImage) {
	// Threshold for percentage of pixels. Adjust as needed.
	const percentageThreshold = 50.0
	for _, testImage := range testImages {
		t.Run(testImage.path, func(t *testing.T) {
			t.Logf("Analyzing %s (HSV):\n", testImage.path)
			file, err := os.Open(testImage.path)
			if err != nil {
				t.Fatalf("could not open image file: %v", err)
			}
			defer file.Close()
			frame, err := io.ReadAll(file)
			if err != nil {
				t.Fatalf("could not read image file: %v", err)
			}
			inBoundsPercentages, err := GetPercentageInBounds(frame, hsvRanges)
			if err != nil {
				t.Fatalf("Error analyzing %s: %v\n", testImage.path, err)
			}
			detectedColor := ""
			maxPercentage := 0.0
			// find the color with the highest percentage of pixels in the range
			// if and only if it is above the threshold
			for color, percentage := range inBoundsPercentages {
				t.Logf("Color: %s, Percentage: %f\n", color, percentage)
				if percentage > maxPercentage && percentage > percentageThreshold {
					detectedColor = color
					maxPercentage = percentage
				}
			}
			if detectedColor != testImage.expectedColor {
				// averaging all the pixels isn't the best way to check the color but
				// at least it will give us some basic idea of the values of the pixels
				// from the image for debugging failures.
				logHSVAverage(t, testImage.path)
				t.Logf("Expected color percentage: %v", inBoundsPercentages[testImage.expectedColor])
				t.Errorf("error analyzing image %s: want: %s, got: %s\n", testImage.path, testImage.expectedColor, detectedColor)
			}
		})
	}
}

// createDummyImage creates a dummy image with the given filename and color for
// testing.
func createDummyImage(filename string, c color.RGBA) {
	img := image.NewRGBA(image.Rect(0, 0, 100, 100))
	for y := 0; y < 100; y++ {
		for x := 0; x < 100; x++ {
			img.Set(x, y, c)
		}
	}

	outFile, err := os.Create(filename)
	if err != nil {
		fmt.Printf("Error creating dummy image %s: %v\n", filename, err)
		return
	}
	defer outFile.Close()
	jpeg.Encode(outFile, img, nil)
}

func TestIsColorInHSVRanges(t *testing.T) {
	testCases := []struct {
		name     string
		hsv      HSV
		hsvRange HSVRange
		expected bool
	}{
		{
			name:     "Wrap around lower hue range",
			hsv:      HSV{H: 340, S: 0.6, V: 0.5},
			hsvRange: HSVRange{Min: HSV{H: 340, S: 0.6, V: 0.5}, Max: HSV{H: 20, S: 1.0, V: 1.0}},
			expected: true,
		},
		{
			name:     "Wrap around upper hue range",
			hsv:      HSV{H: 340, S: 0.6, V: 0.5},
			hsvRange: HSVRange{Min: HSV{H: 20, S: 0.6, V: 0.5}, Max: HSV{H: 20, S: 1.0, V: 1.0}},
			expected: true,
		},
		{
			name:     "Wrap around out of range hue",
			hsv:      HSV{H: 339.99, S: 0.6, V: 0.5},
			hsvRange: HSVRange{Min: HSV{H: 340, S: 0.6, V: 0.5}, Max: HSV{H: 20, S: 1.0, V: 1.0}},
			expected: false,
		},
		{
			name:     "Wrap around lower hue range",
			hsv:      HSV{H: 20.01, S: 0.6, V: 0.5},
			hsvRange: HSVRange{Min: HSV{H: 340, S: 0.6, V: 0.5}, Max: HSV{H: 20, S: 1.0, V: 1.0}},
			expected: false,
		},
		{
			name:     "Hue lower than min",
			hsv:      HSV{H: 21.99},
			hsvRange: HSVRange{Min: HSV{H: 22}, Max: HSV{H: 23}},
			expected: false,
		},
		{
			name:     "Hue higher than max",
			hsv:      HSV{H: 23.01},
			hsvRange: HSVRange{Min: HSV{H: 22}, Max: HSV{H: 23}},
			expected: false,
		},
		{
			name:     "Hue in range",
			hsv:      HSV{H: 22.5},
			hsvRange: HSVRange{Min: HSV{H: 22}, Max: HSV{H: 23}},
			expected: true,
		},
		{
			name:     "Saturation lower than min",
			hsv:      HSV{S: 0.49},
			hsvRange: HSVRange{Min: HSV{S: 0.5}, Max: HSV{S: 0.6}},
			expected: false,
		},
		{
			name:     "Saturation higher than max",
			hsv:      HSV{S: 0.61},
			hsvRange: HSVRange{Min: HSV{S: 0.5}, Max: HSV{S: 0.6}},
			expected: false,
		},
		{
			name:     "Saturation in range",
			hsv:      HSV{S: 0.59},
			hsvRange: HSVRange{Min: HSV{S: 0.5}, Max: HSV{S: 0.6}},
			expected: true,
		},
		{
			name:     "Value lower than min",
			hsv:      HSV{V: 0.49},
			hsvRange: HSVRange{Min: HSV{V: 0.5}, Max: HSV{V: 0.6}},
			expected: false,
		},
		{
			name:     "Value higher than max",
			hsv:      HSV{V: 0.61},
			hsvRange: HSVRange{Min: HSV{V: 0.5}, Max: HSV{V: 0.6}},
			expected: false,
		},
		{
			name:     "Value in range",
			hsv:      HSV{V: 0.59},
			hsvRange: HSVRange{Min: HSV{V: 0.5}, Max: HSV{V: 0.6}},
			expected: true,
		},
	}

	for _, testCase := range testCases {
		// use subtest to make it easier to debug
		t.Run(testCase.name, func(t *testing.T) {
			if got := isColorInHSVRanges(testCase.hsv, testCase.hsvRange); got != testCase.expected {
				t.Errorf("isColorInHSVRanges(%v, %v) = %v, want: %v", testCase.hsv, testCase.hsvRange, got, testCase.expected)
			}
		})
	}
}

func TestRgbToHSV(t *testing.T) {
	tests := []struct {
		r    uint32
		g    uint32
		b    uint32
		want HSV
	}{
		{
			r:    65535,
			g:    0,
			b:    0,
			want: HSV{H: 0, S: 1, V: 1},
		},
		{
			r:    0,
			g:    65535,
			b:    0,
			want: HSV{H: 120, S: 1, V: 1},
		},
		{
			r:    0,
			g:    0,
			b:    65535,
			want: HSV{H: 240, S: 1, V: 1},
		},
		{
			r:    32767,
			g:    32767,
			b:    32767,
			want: HSV{H: 0, S: 0, V: 0.5},
		},
		{
			r:    32767,
			g:    65535,
			b:    32767,
			want: HSV{H: 120, S: .5, V: 1.0},
		},
	}

	floatOpts := cmpopts.EquateApprox(0, 1e-4)
	for _, tc := range tests {
		got := rgbToHSV(tc.r, tc.g, tc.b)
		if diff := cmp.Diff(tc.want, got, floatOpts); diff != "" {
			t.Errorf("rgbToHSV(%v, %v, %v) returned an unexpected diff (-want +got): %v", tc.r, tc.g, tc.b, diff)
		}
	}
}
