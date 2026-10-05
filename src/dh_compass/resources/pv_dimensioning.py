"""
Functions for PV-module calculation
Stand: 10.03.2023
Author: CF, DS, JK & TS
"""
import math

import pandas as pd


def calculate_number_of_modules_pitched_roof(
    module: dict,
    area_lengths: list,
    area_widths: list,
) -> list:
    """
    Calculates number of modules for rooftop pv systems

    Args:
        module (dict): Information on the chosen PV-module including
            "name": Name of module,
            "dim_x": Size of module from left to right [m],
            "dim_y": size of module from top to bottom [m],
            "c_inv": Specific investment cost for one module [€],
            "power": Power of one module [Wp],
            "efficiency": Solar energy conversion efficiency of the module
            "weight": Weight of individual panel [kg],
        area_lengths (list[float]) : Length of surfaces (all areas) from left to right [m]
        area_widths (list[float]):  width of surfaces (all areas) from top to bottom   [m]

    Returns
        num_modules (list): Number of installable modules
    """

    # extract module size from input dictionary
    module_size = [module["dim_x"], module["dim_y"]]

    # possible module orientations
    possible_orientations = ["portrait", "landscape"]

    # initialize output list
    num_modules = [0] * len(area_lengths)

    # loop over all areas to install modules on
    for area_index, area_length in enumerate(area_lengths):
        possible_modules = {orientation: 0 for orientation in possible_orientations}
        area_remaining = {}

        # loop over possible orientations to find the one with the most possible modules
        for orientation_index, orientation in enumerate(possible_orientations):

            # calculate the number of modules that can be installed in x and y direction
            possible_modules_x_direction = math.floor(
                area_length / module_size[orientation_index]
            )
            possible_modules_y_direction = math.floor(
                area_widths[area_index] / module_size[orientation_index - 1]
            )

            # calculate the remaining area after the modules have been installed
            area_remaining[orientation] = [
                area_length
                - (module_size[orientation_index] * possible_modules_x_direction)
            ]
            area_remaining[orientation].append(
                area_widths[area_index]
                - (module_size[orientation_index - 1] * possible_modules_y_direction)
            )

            # calculate the total number of possible modules
            possible_modules[orientation] = (
                possible_modules_x_direction * possible_modules_y_direction
            )

        # determine the orientation with the highest number of possible modules
        max_orientation = max(possible_modules, key=possible_modules.get)

        # add the number of modules of the selected orientation to the output array
        num_modules[area_index] += possible_modules[max_orientation]

        # if there is enough remaining area, install additional modules in the other orientation
        if (
            max_orientation == "portrait"
            and area_remaining[max_orientation][1] >= module_size[0]
        ):
            possible_modules_x_direction = math.floor(
                area_length / module_size[1]
            )
            possible_modules_y_direction = math.floor(
                area_remaining[max_orientation][1] / module_size[0]
            )
            num_modules[area_index] += (
                possible_modules_x_direction * possible_modules_y_direction
            )

        elif area_remaining[max_orientation][0] >= module_size[0]:
            possible_modules_x_direction = math.floor(
                area_remaining[max_orientation][0] / module_size[0]
            )
            possible_modules_y_direction = math.floor(
                area_widths[area_index] / module_size[1]
            )
            num_modules[area_index] += (
                possible_modules_x_direction * possible_modules_y_direction
            )

    return num_modules


def calculate_number_of_modules_flat_roof(
    module: dict,
    area_lengths: list,
    area_widths: list,
    roof_orientation: int,
    inclination: int = 15,
    elevation_angles: pd.DataFrame = pd.DataFrame()
) -> list:
    """Calculates number of modules for flat-roof PV systems

    Args:
        module (dict): Dictionary containing module dimensions (dim_x and dim_y).
        area_lengths (list): List of roof surface lengths in meters.
        area_widths (list): List of roof surface widths in meters.
        roof_orientation (int): Angle of roof orientation in degrees (0 to 45).
        inclination (int): Angle of panel inclination in degrees (0 to 90).
        elevation_angles (pd.DataFrame): DataFrame containing elevation angles for the sun.

    Returns:
        list : A list containing the number of modules that can fit on each roof surface.
    """

    # extract module size from input dictionary
    module_size = [module["dim_x"], module["dim_y"]]

    # possible module orientations
    possible_orientations = ["landscape", "portrait"]

    # initialize output array
    final_num_modules = [0] * len(area_lengths)

    # check, if roof orientation angle is given between 0 and 45 degrees, if not, force it to be
    if not 0 <= roof_orientation <= 45:
        roof_orientation = roof_orientation % 45

    # calculate angles in radians
    alpha, beta = math.radians(roof_orientation), math.radians(90 - roof_orientation)

    # iterate over all surfaces
    for area_index, area_length in enumerate(area_lengths):
        # calculate distance between the PV-system and the ground
        dist_north_south = area_length * math.sin(alpha) + area_widths[area_index] * math.sin(beta)
        possible_modules = {orientation: 0 for orientation in possible_orientations}

        # iterate over possible module orientations
        for orientation_index, orientation in enumerate(possible_orientations):
            shadow_cast_modules = module_size[orientation_index] * math.cos(math.radians(inclination)) + \
                                         max(0.1, module_size[orientation_index] * math.sin(math.radians(inclination)) /
                                             math.tan(elevation_angles['sun_alt']['2012-12-21 12:00:00']))
            # calculate the number of rows that can fit on the surface
            num_rows = int(dist_north_south // shadow_cast_modules)

            # iterate over rows and calculate number of modules that can fit in each row
            for j in range(num_rows):
                row_height = (j + 1) * shadow_cast_modules

                # triangle south
                if row_height < (math.cos(beta) * area_length):
                    panels_per_row = math.floor(
                        (row_height * math.tan(alpha) + row_height * math.tan(beta))
                        / module_size[orientation_index]
                    )

                # parallelogram
                elif row_height < (dist_north_south - math.cos(beta) * area_length):
                    panels_per_row = math.floor(
                        (
                            math.sin(beta) * area_length
                            + math.tan(alpha) * math.cos(beta) * area_length
                        )
                        / module_size[orientation_index]
                    )

                # triangle north
                else:
                    row_height = dist_north_south - row_height
                    panels_per_row = math.floor(
                        (row_height * math.tan(beta) + row_height * math.tan(alpha))
                        / module_size[orientation_index]
                    )

                possible_modules[orientation] += panels_per_row

        final_num_modules[area_index] = max(possible_modules.values())

    return final_num_modules
