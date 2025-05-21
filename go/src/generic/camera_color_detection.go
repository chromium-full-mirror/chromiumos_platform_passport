// Copyright 2025 The ChromiumOS Authors
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

// Package generic provides plugins for controlling generic devices (not vendor specific).
package generic

import (
	"bytes"
	"fmt"
	"image"
	"math"
)

// HSV represents a color in the Hue, Saturation, Value color space.
type HSV struct {
	H, S, V float64 // H: [0, 360), S: [0, 1], V: [0, 1]
}

type HSVRange struct {
	Min, Max HSV
}

// rgbToHSV converts an RGB color to HSV.
// R, G, B are assumed to be in the range [0, 255].
func rgbToHSV(r, g, b uint32) HSV {
	// image.Color returns uint32 RGB values, scale those to 0-1 float64 value
	rF := float64(r) / 65535.0
	gF := float64(g) / 65535.0
	bF := float64(b) / 65535.0

	max := math.Max(rF, math.Max(gF, bF))
	min := math.Min(rF, math.Min(gF, bF))
	delta := max - min

	h := 0.0
	if delta == 0 {
		h = 0.0 // achromatic
	} else if max == rF {
		h = math.Mod((gF-bF)/delta, 6) * 60
	} else if max == gF {
		h = ((bF-rF)/delta + 2) * 60
	} else { // max == bF
		h = ((rF-gF)/delta + 4) * 60
	}
	if h < 0 {
		h += 360
	}

	s := 0.0
	if max != 0 {
		s = delta / max
	}

	v := max

	return HSV{H: h, S: s, V: v}
}

// isColorInHSVRanges checks if an HSV color falls within the defined ranges
// for a target color.
func isColorInHSVRanges(hsv HSV, hsvRange HSVRange) bool {
	// Check saturation and value first
	if hsv.S < hsvRange.Min.S || hsv.V < hsvRange.Min.V {
		return false
	}
	if hsv.S > hsvRange.Max.S || hsv.V > hsvRange.Max.V {
		return false
	}
	// finally check hue
	if hsvRange.Min.H < hsvRange.Max.H {
		// case when we have a normal range
		if hsv.H < hsvRange.Min.H || hsv.H > hsvRange.Max.H {
			return false
		}
	} else {
		// case when we have a range that wraps around the hue range
		if hsv.H < hsvRange.Min.H && hsv.H > hsvRange.Max.H {
			return false
		}
	}
	return true
}

// GetPercentageInBounds analyzes an image to determine its the percentage of
// pixels in each of the given HSV ranges.
func GetPercentageInBounds(frame []byte, hsvRanges map[string]HSVRange) (map[string]float64, error) {
	img, _, err := image.Decode(bytes.NewReader(frame))
	if err != nil {
		return nil, fmt.Errorf("could not decode image from bytes: %w", err)
	}

	bounds := img.Bounds()
	totalPixels := bounds.Dx() * bounds.Dy()
	if totalPixels == 0 {
		return nil, fmt.Errorf("image is empty, width: %v, height: %v", bounds.Dx(), bounds.Dy())
	}

	inBoundsPixelsByName := make(map[string]float64)
	// Iterate through all pixels and check if they are in the given ranges.
	for y := bounds.Min.Y; y < bounds.Max.Y; y++ {
		for x := bounds.Min.X; x < bounds.Max.X; x++ {
			r, g, b, _ := img.At(x, y).RGBA()
			hsv := rgbToHSV(r, g, b)
			for rangeName, hsvRange := range hsvRanges {
				if isColorInHSVRanges(hsv, hsvRange) {
					inBoundsPixelsByName[rangeName]++
					break
				}
			}
		}
	}
	inBoundsPercentages := make(map[string]float64)
	for rangeName, inBoundsPixel := range inBoundsPixelsByName {
		inBoundsPercentage := float64(inBoundsPixel) / float64(totalPixels) * 100
		inBoundsPercentages[rangeName] = inBoundsPercentage
	}
	return inBoundsPercentages, nil
}
