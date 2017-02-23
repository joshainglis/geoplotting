import logging
import sys
from os import getenv
from os.path import exists, join

import geopandas as gpd
import geoplot as gplt
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
from geopandas import GeoDataFrame, GeoSeries
from typing import Callable, Tuple
from yaml import safe_load

from interviz.helpers.raster_to_polygons import (
    generate_viewshed_polygons,
)

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger('__name__')

PROJECTION = gplt.crs.TransverseMercator()


def reader(input_path: str, output_path: str, transform: Callable[[GeoDataFrame], GeoDataFrame],
           overwrite: bool = False):
    if output_path and exists(output_path) and not overwrite:
        return gpd.read_file(output_path)
    else:
        df = transform(gpd.read_file(input_path))
        df.to_file(output_path)
        return df


def transform_viewpoints(viewpoints: GeoDataFrame) -> GeoDataFrame:
    viewpoints['FID'] = viewpoints.FID_split - 1
    viewpoints = viewpoints[['FID', 'Z', 'geometry']].set_index('FID', drop=False, verify_integrity=True)
    return viewpoints


def transform_islands(islands: GeoDataFrame) -> GeoDataFrame:
    islands.geometry = islands.buffer(0)
    islands = islands[['Id', 'geometry']]
    islands['FID'] = islands.Id - 1
    islands = islands.set_index('FID', drop=False, verify_integrity=True)
    return islands


def transform_split_islands(split_islands: GeoDataFrame) -> GeoDataFrame:
    split_islands = split_islands[['Id', 'geometry']]
    split_islands['FID_island'] = split_islands.Id - 1
    return split_islands


def join_viewpoints_to_split_islands(
        islands_df: GeoDataFrame,
        viewpoints: GeoDataFrame,
        split_islands: GeoDataFrame,
        output_path: str,
        overwrite: bool = False
) -> GeoDataFrame:
    if output_path and exists(output_path) and not overwrite:
        return gpd.read_file(output_path)
    else:
        jvp = viewpoints.join(split_islands[['FID_island']], on='FID', how='inner')
        jvp = jvp[['FID_island', 'Z', 'geometry']]
        ivp = jvp.join(islands_df, on='FID_island', rsuffix='_island')[
            ['FID_island', 'Z', 'geometry']]
        ivp.to_file(output_path)
        return ivp


def get_islands_and_island_viewpoints(
        island_viewpoints_output_path: str,
        island_input_path: str,
        viewpoint_input_path: str,
        split_island_input_path: str,
        island_output_path: str,
        viewpoint_output_path: str,
        split_island_output_path: str,
        overwrite: bool = False
) -> Tuple[GeoDataFrame, GeoDataFrame]:
    if island_viewpoints_output_path and exists(island_viewpoints_output_path) and not overwrite:
        return gpd.read_file(island_output_path), gpd.read_file(island_viewpoints_output_path)
    else:
        islands = reader(island_input_path, island_output_path, transform_islands, overwrite=overwrite)
        viewpoints = reader(viewpoint_input_path, viewpoint_output_path, transform_viewpoints, overwrite=overwrite)
        split_islands = reader(
            split_island_input_path, split_island_output_path, transform_split_islands, overwrite=overwrite
        )
        return islands, join_viewpoints_to_split_islands(
            islands, viewpoints, split_islands, island_viewpoints_output_path, overwrite=overwrite
        )


def fix_poly_viewsheds(poly_viewsheds_shapefile: str, poly_viewsheds_output: str) -> GeoDataFrame:
    poly_viewsheds = gpd.read_file(poly_viewsheds_shapefile)
    poly_viewsheds['geometry'] = poly_viewsheds.buffer(0)
    poly_viewsheds['area'] = poly_viewsheds.geometry.area
    poly_viewsheds = poly_viewsheds.dissolve(by='FID_island')
    poly_viewsheds_tmp = poly_viewsheds.buffer(0)
    poly_viewsheds_tmp.crs = {'init': 'epsg:4326'}
    poly_viewsheds.geometry = poly_viewsheds_tmp
    poly_viewsheds.to_file(poly_viewsheds_output)
    return poly_viewsheds


def spatial_join(left: GeoDataFrame, right: GeoDataFrame, output_path: str, overwrite: bool = False) -> GeoDataFrame:
    if output_path and exists(output_path) and not overwrite:
        return gpd.read_file(output_path)
    else:
        joined = gpd.sjoin(left, right)
        joined.to_file(output_path)
        return joined


def fix_islands_viewsheds_join(r: GeoDataFrame, output_path: str) -> GeoDataFrame:
    if output_path and exists(output_path) and not overwrite:
        return gpd.read_file(output_path)
    else:
        r['idx_island'] = r.Id - 1
        r['idx_viewshed'] = r.index_righ
        r_unique = r[r.idx_island != r.idx_viewshed]
        r_unique = r_unique.reset_index().set_index(['idx_viewshed', 'idx_island'])
        return r_unique


def create_intersection_graph(
        islands_viewsheds_joined_df: GeoDataFrame,
        poly_viewsheds_df: GeoDataFrame,
        islands_df: GeoDataFrame) -> nx.DiGraph:
    G = nx.DiGraph()
    for idx, (i, row) in enumerate(islands_viewsheds_joined_df.reset_index().iterrows()):
        if i % 500 == 0:
            print(i)
        intersect = poly_viewsheds_df.loc[row['idx_viewshed']].geometry.intersection(
            islands_df.loc[row['idx_island']].geometry)  # type: GeoSeries
            intersect.unary_union
        G.add_edge(row['idx_viewshed'], row['idx_island'], area=intersect.area, region=intersect)
    return G


def create_island_to_island_graph(g: nx.DiGraph) -> nx.DiGraph:
    GG = nx.DiGraph()
    for node_a, node_b in g.edges_iter():
        if node_a in g.edge[node_b]:
            GG.add_edge((node_a, node_b), (node_b, node_a))
            cab = g.edge[node_a][node_b]['region'].centroid
            GG.node[(node_a, node_b)]['coord'] = (cab.x, cab.y)
    nx.write_shp()
    return GG


def create_geodataframe_from_graph(island_graph: nx.DiGraph, island_to_island_graph: nx.DiGraph) -> GeoDataFrame:
    df = GeoDataFrame([
        {
            'idx_a': node_a,
            'idx_b': node_b,
            'geometry': island_graph[node_a][node_b]['region']
        } for node_a, node_b in island_to_island_graph.nodes_iter()
    ], geometry='geometry', crs=islands.crs)
    return df


def fix_island_to_island_df(island_to_island_df: GeoDataFrame) -> GeoDataFrame:
    i2idf_reindexed = island_to_island_df.set_index(['idx_a', 'idx_b']).buffer(0)
    i2idf_reindexed[i2idf_reindexed.apply(lambda x: not x.is_empty and x.area > 1e-9)].area.sort_values(ascending=True)
    return i2idf_reindexed


def pretty_plot(gg: GeoDataFrame, islands: GeoDataFrame, poly_viewsheds: GeoDataFrame, save_figure_to: str,
                proj=PROJECTION):
    x = gg[gg.apply(lambda x: not x.is_empty and x.area > 1e-9)]
    xa = GeoDataFrame(x.centroid, geometry=0, crs=islands.crs)
    xa.columns = ['geometry']
    xa_tmp = xa.reset_index()
    xa_tmp['idx'] = xa_tmp.apply(lambda y: (y.idx_a, y.idx_b), axis=1)
    xa_tmp['idx_other'] = xa_tmp.apply(lambda y: (y.idx_b, y.idx_a), axis=1)
    xa_tmp = xa_tmp.set_index('idx')
    paths = xa_tmp.join(xa_tmp, on='idx_other', lsuffix='_ab', rsuffix='_ba')
    paths = paths[paths.apply(lambda y: y.geometry_ab is not np.nan and y.geometry_ba is not np.nan, axis=1)]

    ax = gplt.polyplot(
        islands,
        projection=proj,
        figsize=(20, 20),
        color='darkgray'
    )
    gplt.polyplot(
        poly_viewsheds,
        projection=proj,
        ax=ax,
        linewidth=0,
        facecolor='lightgray',
        alpha=0.3
    )
    gplt.polyplot(
        x,
        projection=proj,
        ax=ax,
        linewidth=0,
        facecolor='red',
        alpha=0.3
    )
    gplt.sankey(
        paths,
        start='geometry_ab',
        end='geometry_ba',
        ax=ax,
        projection=proj,
        alpha=0.05,
        rasterized=False
    )

    plt.savefig(save_figure_to)


# pos = {node: GG.node[node]['coord'] for node in GG.nodes_iter()}
#
# rr = r_unique[['index_right']]
# r_unique['geometry'] = r_unique.apply(lambda row: G[row.name[0]][row.name[1]]['region'], axis=1)
# r_unique = r_unique[['geometry']].apply(lambda row: (G[row.name[0]][row.name[1]]['region'],), axis=1)
# rr = gpd.GeoDataFrame(rr)


if __name__ == '__main__':
    with open(getenv('CONFIG_PATH', 'config.yml')) as f:
        config = safe_load(f)
    print(config)
    overwrite = config['overwrite']
    data_path = config['env']['data']
    scratch_path = config['env']['scratch']

    island_input_path = join(data_path, config['raw_files']['islands']['input'])
    viewpoint_input_path = join(data_path, config['raw_files']['viewpoints']['input'])
    split_island_input_path = join(data_path, config['raw_files']['split_islands']['input'])

    island_output_path = join(scratch_path, config['raw_files']['islands']['output'])
    viewpoint_output_path = join(scratch_path, config['raw_files']['viewpoints']['output'])
    split_island_output_path = join(scratch_path, config['raw_files']['split_islands']['output'])
    island_viewpoints_output_path = join(scratch_path, config['generated_files']['island_viewpoints']['output'])

    viewshed_folder = join(data_path, config['raw_files']['viewsheds']['rasters']['input_folder'])
    viewshed_regex = config['raw_files']['viewsheds']['rasters']['regex']
    viewsheds_per_file = config['raw_files']['viewsheds']['rasters']['viewsheds_per_file']
    viewsheds_overflow = config['raw_files']['viewsheds']['rasters']['overflow']

    viewshed_polygons_output = join(
        scratch_path, config['generated_files']['viewsheds']['polygons']['raw_output'])
    viewshed_polygons_output_fixed = join(
        scratch_path, config['generated_files']['viewsheds']['polygons']['fixed_output'])

    islands_viewsheds_joined_output = join(
        scratch_path, config['generated_files']['islands_viewsheds_joined']['raw_output'])
    islands_viewsheds_joined_fixed_output = join(
        scratch_path, config['generated_files']['islands_viewsheds_joined']['fixed_output'])

    islands, joined_viewpoints = get_islands_and_island_viewpoints(
        island_viewpoints_output_path=island_viewpoints_output_path,
        island_input_path=island_input_path,
        island_output_path=island_output_path,
        viewpoint_input_path=viewpoint_input_path,
        viewpoint_output_path=viewpoint_output_path,
        split_island_input_path=split_island_input_path,
        split_island_output_path=split_island_output_path,
        overwrite=overwrite
    )
    if not overwrite and exists(viewshed_polygons_output_fixed):
        poly_viewsheds = gpd.read_file(viewshed_polygons_output_fixed)
    else:
        generate_viewshed_polygons(
            input_folder=viewshed_folder,
            input_viewpoint_shapefile=joined_viewpoints,
            output_file=viewshed_polygons_output,
            viewshed_file_regex=viewshed_regex,
            viewsheds_per_file=viewsheds_per_file,
            overflow=viewsheds_overflow,
        )
        poly_viewsheds = fix_poly_viewsheds(viewshed_polygons_output, viewshed_polygons_output_fixed)

    r = spatial_join(islands, poly_viewsheds, islands_viewsheds_joined_output, overwrite=overwrite)
    r = fix_islands_viewsheds_join(r, islands_viewsheds_joined_fixed_output)
    G = create_intersection_graph(r, poly_viewsheds, islands)
    GG = create_island_to_island_graph(G)
    fix_island_to_island_df(create_geodataframe_from_graph(G, GG))
