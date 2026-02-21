# Media Formats Reference

This page lists the MusicBrainz release formats grouped into the meta-format buckets used by LM Bridge filtering.

Notes:

- Meta-format keys are the filter tokens (shown in parentheses).
- Format names are the exact MusicBrainz release format values.
- Release counts are from the MusicBrainz mirror, as of Jan 2026.
- Substring matching is supported, so a partial term can match multiple formats (for example, `vinyl` matches `12" Vinyl`, `10" Vinyl`, and `7" Vinyl`).
- Some formats are intentional aliases (for example, `CD` and `Compact Disc`); these remain listed as distinct values.
- Case- or diacritic-only variants are collapsed in this document for readability.

## Digital

### Hi-Res (digital_hi_res)

| Format                                 | Releases |
| -------------------------------------- | -------: |
| Blu-ray                                |    6,947 |
| Hybrid SACD                            |    4,965 |
| HDCD                                   |    3,932 |
| SACD                                   |    3,209 |
| Hybrid SACD (SACD layer, 2 channels)   |    2,181 |
| Hybrid SACD (SACD layer, multichannel) |    1,149 |
| DVD-Audio                              |    1,004 |
| Hybrid SACD (SACD layer)               |      542 |
| SACD (2 channels)                      |      304 |
| SHM-SACD                               |      288 |
| SHM-SACD (2 channels)                  |      138 |
| SACD (multichannel)                    |       98 |
| DualDisc (DVD-Audio side)              |       89 |
| Blu-ray-R                              |       28 |
| HD-DVD                                 |       10 |
| DVDplus (DVD-Audio side)               |        4 |
| Ultra HD Blu-ray                       |        3 |
| MiniDVD-Audio                          |        1 |
| Minimax DVD-Audio                      |        1 |
| SHM-SACD (multichannel)                |        1 |

### CD Quality (digital_cd_quality)

| Format                 |  Releases |
| ---------------------- | --------: |
| Digital Media          | 2,506,866 |
| CD                     | 2,158,615 |
| CD-R                   |    65,832 |
| Enhanced CD            |    12,163 |
| 8cm CD                 |    11,387 |
| SHM-CD                 |     4,512 |
| Copy Control CD        |     3,498 |
| Hybrid SACD (CD layer) |     2,666 |
| Data CD                |     1,930 |
| Blu-spec CD            |     1,642 |
| HQCD                   |     1,067 |
| Mixed Mode CD          |       911 |
| DAT                    |       651 |
| CD+G                   |       348 |
| DualDisc (CD side)     |       283 |
| CDV                    |       173 |
| DTS CD                 |       146 |
| 8cm CD+G               |       131 |
| Minimax CD             |        54 |
| 8cm CD-R               |        31 |
| DVDplus (CD side)      |        14 |
| Compact Disc           |         - |

### Video Optical (digital_video_optical)

| Format                    | Releases |
| ------------------------- | -------: |
| DVD-Video                 |   29,384 |
| DVD                       |    8,670 |
| VCD                       |      470 |
| DualDisc                  |      208 |
| DVD-R Video               |      199 |
| DualDisc (DVD-Video side) |      190 |
| Data DVD                  |       99 |
| Data DVD-R                |       66 |
| DualDisc (DVD side)       |       17 |
| DVDplus (DVD-Video side)  |       15 |
| UMD                       |       14 |
| CD-i                      |       10 |
| DVDplus                   |        8 |
| SVCD                      |        5 |
| MiniDVD                   |        2 |
| MiniDVD-Video             |        1 |
| Minimax DVD-Video         |        1 |
| Minimax DVD               |        - |

### Compressed or Legacy (digital_compressed_or_legacy)

| Format   | Releases |
| -------- | -------: |
| MiniDisc |      350 |
| DCC      |       32 |

### Legacy Media (digital_legacy_media)

| Format            | Releases |
| ----------------- | -------: |
| USB Flash Drive   |    1,183 |
| Download Card     |    1,181 |
| 3.5" Floppy Disk  |       88 |
| KiT Album         |       81 |
| ROM cartridge     |       40 |
| Playbutton        |       39 |
| SD Card           |       28 |
| Floppy Disk       |       17 |
| microSD           |       16 |
| DataPlay          |       12 |
| slotMusic         |        8 |
| 5.25" Floppy Disk |        3 |
| Zip Disk          |        3 |

### Other Unknown (digital_other_unknown)

| Format  | Releases |
| ------- | -------: |
| Other   |      929 |
| Unknown |        - |

## Analog

### Vinyl (analog_vinyl)

| Format    | Releases |
| --------- | -------: |
| 12" Vinyl |  429,228 |
| 7" Vinyl  |  152,932 |
| Vinyl     |   40,011 |
| 10" Vinyl |   10,943 |
| 3" Vinyl  |       39 |

### Other Discs (analog_other_discs)

| Format                 | Releases |
| ---------------------- | -------: |
| Phonograph record      |    1,085 |
| 7" Flexi-disc          |    1,050 |
| Flexi-disc             |      293 |
| Edison Diamond Disc    |      161 |
| VinylDisc              |       48 |
| Pathé disc             |       30 |
| VinylDisc (CD side)    |       12 |
| VinylDisc (Vinyl side) |       12 |
| VinylDisc (DVD side)   |        1 |

### Tape (analog_tape)

| Format            | Releases |
| ----------------- | -------: |
| Cassette          |   80,758 |
| Reel-to-reel      |      554 |
| 8-Track Cartridge |      545 |
| Cartridge         |       79 |
| Microcassette     |       57 |
| PlayTape          |       10 |
| HiPac             |        1 |

### Video (analog_video)

| Format        | Releases |
| ------------- | -------: |
| VHS           |    1,326 |
| LaserDisc     |      173 |
| 12" LaserDisc |      113 |
| Betacam SP    |       40 |
| Betamax       |       38 |
| VHD           |       11 |
| CED           |        4 |
| 8" LaserDisc  |        3 |

### Acetate (analog_acetate)

| Format      | Releases |
| ----------- | -------: |
| 10" Acetate |      139 |
| 12" Acetate |      101 |
| 7" Acetate  |       39 |
| Acetate     |       34 |

### Shellac (analog_shellac)

| Format      | Releases |
| ----------- | -------: |
| 10" Shellac |   26,459 |
| Shellac     |      686 |
| 12" Shellac |      462 |
| 7" Shellac  |      117 |

### Mechanical (analog_mechanical)

| Format       | Releases |
| ------------ | -------: |
| Wax Cylinder |    3,377 |
| Piano Roll   |      169 |
| Tefifon      |        1 |
