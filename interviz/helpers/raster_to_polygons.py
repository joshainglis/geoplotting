import logging
import re
from os import getenv, listdir
from os.path import exists, join

import fiona
import rasterio
import rasterio.windows as rws
from geopandas import GeoDataFrame, read_file
from numpy import bitwise_and, bool_, ndarray, uint8
from rasterio import Affine, DatasetReader
from rasterio.features import shapes
from typing import Iterable, Mapping, Tuple, Union

logger = logging.getLogger(__name__)

VIEWSHEDS_PER_FILE = int(getenv('VIEWSHEDS_PER_FILE', 32))
OVERFLOW = int(getenv('OVERFLOW', 31))


# noinspection PyUnresolvedReferences
def save_to_shapefile(
        poly_generator: Iterable[Mapping],
        raster: DatasetReader,
        vector_file: str
) -> None:
    mode = 'w' if not exists(vector_file) else 'a'
    with fiona.open(
            vector_file, mode,
            driver="ESRI Shapefile",
            crs=raster.crs.data,
            schema={
                'properties': [('raster_val', 'int'), ('FID_island', 'int'), ('FID_point', 'int')],
                'geometry': 'Polygon'
            }
    ) as dst:
        dst.writerecords(poly_generator)


# noinspection PyUnresolvedReferences
def raster_to_poly(
        viewshed_raster: ndarray,
        viewshed_mask: ndarray,
        viewpoint: int,
        island: int,
        transform: Affine,
        connectivity: int = 8
) -> Iterable[Mapping]:
    return (
        {'properties': {'raster_val': v, 'FID_island': island, 'FID_point': viewpoint}, 'geometry': s} for s, v
        in shapes(viewshed_raster, mask=viewshed_mask, connectivity=connectivity, transform=transform)
    )


def separate_viewshed(
        vs_index: int,
        overflow: int,
        viewshed_layer: ndarray,
        valid_data_mask: ndarray
) -> Tuple[ndarray, ndarray]:
    val = 1 if vs_index < overflow else -1
    mask = bitwise_and(viewshed_layer, (val << vs_index)).astype(bool_) & valid_data_mask
    img = mask.astype(uint8)
    #     logger.info("index: %d, mask: %d, img: %d", vs_index, mask.sum(), img.sum())

    return img, mask


def separate_viewsheds(
        viewsheds_per_file: int,
        overflow: int,
        viewshed_layer: ndarray,
        valid_data_mask: ndarray,
        vector_file: str,
        raster: DatasetReader,
        vs_num: int,
        transform: Affine,
        viewpoints_df: GeoDataFrame
) -> None:
    for vs_index in range(viewsheds_per_file):
        viewpoint = ((vs_num - 1) * 32) + vs_index
        island = int(viewpoints_df.iloc[viewpoint].FID_island)
        img, mask = separate_viewshed(vs_index, overflow, viewshed_layer, valid_data_mask)
        if img.sum() > 0:
            poly_generator = raster_to_poly(img, mask, viewpoint, island, transform)
            save_to_shapefile(poly_generator, raster, vector_file)


def disaggregate_viewsheds_and_convert_to_polygons(
        raster_file: str,
        vector_file: str,
        viewpoints_df: GeoDataFrame,
        vs_num: int,
        viewsheds_per_file: int = VIEWSHEDS_PER_FILE,
        overflow: int = OVERFLOW,
        use_windowing: bool = True
) -> None:
    with rasterio.open(raster_file) as raster:
        logger.info("%s", raster_file)
        if use_windowing:
            for i, (ji, window) in enumerate(raster.block_windows(1)):
                transform = rws.transform(window=window, transform=raster.transform)
                if i % 50000 == 0:
                    logger.info("%s %d", raster_file, i)
                try:
                    viewshed_layer = raster.read(1, window=window)  # type: ndarray
                except Exception as e:
                    continue
                nodata_value = int(raster.nodatavals[0])
                valid_data_mask = viewshed_layer != nodata_value
                if valid_data_mask.sum() > 0:
                    separate_viewsheds(viewsheds_per_file, overflow, viewshed_layer, valid_data_mask, vector_file,
                                       raster, vs_num, transform, viewpoints_df)
        else:
            viewshed_layer = raster.read(1)  # type: ndarray
            nodata_value = int(raster.nodatavals[0])
            valid_data_mask = viewshed_layer != nodata_value
            if valid_data_mask.sum() > 0:
                separate_viewsheds(viewsheds_per_file, overflow, viewshed_layer, valid_data_mask, vector_file,
                                   raster, vs_num, raster.transform, viewpoints_df)


def generate_viewshed_polygons(
        input_folder: str,
        input_viewpoint_shapefile: Union[str, GeoDataFrame],
        output_file: str,
        viewshed_file_regex: str,
        viewsheds_per_file: int,
        overflow: int
):
    if isinstance(input_viewpoint_shapefile, GeoDataFrame):
        viewpoints = input_viewpoint_shapefile
    else:
        viewpoints = read_file(input_viewpoint_shapefile)

    vs_re = re.compile(viewshed_file_regex)
    for viewshed_file in sorted(y for y in listdir(input_folder) if vs_re.match(y)):
        vs_num = int(vs_re.match(viewshed_file).group(1))
        raster_file = join(input_folder, viewshed_file)
        try:
            disaggregate_viewsheds_and_convert_to_polygons(raster_file, output_file, viewpoints, vs_num,
                                                           viewsheds_per_file=viewsheds_per_file, overflow=overflow)
        except IndexError:
            continue
