# NIST AM-Bench 2018-02 Process Metadata Provenance

## Purpose

The trace-level process table uses the calibrated AMMT laser power that physically produced each track. A separate machine-context record preserves the official commanded-power and laser-spot-size corrections without treating those values as additional process conditions or response measurements.

Machine-readable context:

- `process_metadata_context.json`

The component-level and representative NIST workflows continue to read the active trace-level process table for calculations. This context remains supplemental provenance and does not create additional workflow inputs, conditions, or response features.

## Laser-power correction

NIST reports that AMMT laser calibration was found to be erroneous after the tracks were fabricated.

| Case | Commanded power | Actual calibrated power | Scan speed |
|---|---:|---:|---:|
| A | 150.0 W | 137.9 W | 400 mm/s |
| B | 195.0 W | 179.2 W | 800 mm/s |
| C | 195.0 W | 179.2 W | 1200 mm/s |

The existing process–characterization workflow continues to use `actual_laser_power_w`. Commanded power is preserved only as provenance and must not be substituted for the actual value.

## Laser-spot-size correction

The legacy AMMT cross-section table displays a laser spot size of 45 µm FWHM. NIST later reported the true AMMT spot as:

- 170 µm D4σ diameter;
- 100 µm FWHM.

Both the legacy and corrected values are preserved so downstream readers do not silently mix obsolete and corrected definitions.

The correction does not revise the source-reported melt-pool geometry measurements. It also does not make the current `actual_laser_power_w / scan_speed_mm_s` descriptor volumetric energy density. Spot size, absorptivity, thermal boundary conditions, and material response remain outside that descriptor.

## Source boundary

Official sources:

- `https://www.nist.gov/ambench/amb2018-02-description`
- `https://www.nist.gov/ambench/challenges-and-descriptions`
- `https://www.nist.gov/ambench/chal-amb2018-02-mp-xsection`
- dataset DOI `10.18434/mds2-3830`
- associated publication DOI `10.1007/s40192-020-00169-1`

The context values are a manual transcription from official NIST pages. They are not raw controller logs, independent beam measurements, or a remeasurement of the optical microscopy files.

## Scientific boundary

**Evidence level: Diagnostic**

The metadata supports provenance and physically correct interpretation of the three existing conditions. It does not support causal separation of commanded power, actual power, scan speed, or spot size; predictive modeling; optimization; volumetric energy-density claims; or engineering-release decisions.
