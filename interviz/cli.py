import click
import geopandas as gpd

from interviz.helpers.raster_to_polygons import generate_viewshed_polygons


@click.command()
@click.argument('input-folder', type=click.Path(exists=True, dir_okay=True, file_okay=False, resolve_path=True))
@click.argument('input-viewpoint-shapefile',
                type=click.Path(exists=True, dir_okay=False, file_okay=True, resolve_path=True))
@click.argument('output-file', type=click.Path(exists=False, dir_okay=False, file_okay=True, resolve_path=True))
@click.option('--viewshed-file-regex', '-v', default='^viewshed_(\d+)$', type=click.STRING)
@click.option('--viewsheds-per-file', '-n', default=32, type=click.INT)
@click.option('--overflow', '-f', default=31, type=click.INT)
def generate_viewshed_polygons_cli(input_folder, input_viewpoint_shapefile, output_file, viewshed_file_regex,
                                   viewsheds_per_file, overflow):
    generate_viewshed_polygons(input_folder, input_viewpoint_shapefile, output_file, viewshed_file_regex,
                               viewsheds_per_file, overflow)


@click.command()
@click.argument('islands', type=click.Path(exists=True, dir_okay=False, resolve_path=True))
@click.argument('viewsheds', type=click.Path(exists=True, dir_okay=False, resolve_path=True))
@click.argument('output', type=click.Path(exists=False, dir_okay=False, resolve_path=True))
def spatial_join(islands, viewsheds, output):
    islands = gpd.read_file(islands)
    islands['FID'] = islands.Id - 1
    islands = islands.set_index('FID')

    poly_viewsheds = gpd.read_file(viewsheds)

    r = gpd.sjoin(islands, poly_viewsheds)
    r.to_file(output)
