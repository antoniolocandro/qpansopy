# qpansopy
An opensource PANS OPS software implementation based on QGIS

***Note: This code is in development and provided as is, it may contain errors and you are solely resposible for using it. Any feedback is welcome.***

* The implementation is done in a projected coordinate system and currently there is no intention to use a purely geodesic calculation.  
* All computations are done in meters and KTS thus conversions are done when needed.
* Use of references layers vs rubberbands (point/click on map to get values) is currently used, this may be changed in the future.
* PANS OPS has "equivalences" that are not really equivalent like 50 ft = 15 m so you would expect some differences due to this.

## Currently in implementation
***main initial focus is area creation, evaluation to be added at later stage***

### Utilities 
- VSS Tool
- Wind Spiral Tool
- Object Selection (Extract points intersecting area)
- Point Filter
- Flash Feature Merge
### Conventional Approach
- VOR template
- NDB template
- Conventional Initial Template
### Precision Approach
- ILS Basic Surfaces
- ILS OAS CAT I
### PBN Approach
- PBN LNAV (straight to runway)
- PBN intermediate (aligned)
- PBN initial (without automatic connection to the intermediate)
- PBN Missed Approach (simple straight ahead)
## Next Steps 
- PBN 15 NM and 30 NM targets

## Roadmap
- Initial focus in correct area creation
- Ability to export tables to Word for creating reports
- Add evaluation of straight segments
- Add logic for evaluation of curves/offsets

## Sponsors
This project is funded by the inkind contributions of FLYGHT7 and the following donors:  
<img src="https://github.com/user-attachments/assets/91fcad9c-cc35-48c0-b333-a2fb7f39bd10" width="150" height="150">

