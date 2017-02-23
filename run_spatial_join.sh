#!/usr/bin/env bash

source ~/anaconda3/bin/activate geoplotting
interviz-spatial-join data/ISEA/Full_VS/sl_-85/islands_fixed.shp data/ISEA/Full_VS/poly_viewsheds_dissolved.shp data/ISEA/Full_VS/poly_viewsheds_joined.shp

echo "DONE!"
