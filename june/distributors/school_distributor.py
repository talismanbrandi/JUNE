import logging
from typing import List, Tuple

import numpy as np
import yaml
from scipy import stats

from june import paths
from june.demography.geography import Area, SuperArea, Geography
from june.groups.school import Schools

default_data_filename = paths.data_path / "processed/school_data/england_schools_data.csv"
default_areas_map_path = paths.data_path / "processed/geographical_data/oa_msoa_region.csv"
default_config_filename = paths.configs_path / "defaults/distributors/school_distributor.yaml"

logger = logging.getLogger(__name__)

EARTH_RADIUS = 6371  # km

default_decoder = {
    2314: "secondary",
    2315: "primary",
    2316: "special_needs",
}


class SchoolDistributor:
    """
    Distributes students in an area to different schools 
    """

    def __init__(
            self,
            schools: Schools,
            education_sector_label: List[int] = [2314, 2315, 2316],
            neighbour_schools: int = 35,
            age_range: Tuple[int, int] = (0, 19),
            mandatory_age_range: Tuple[int, int] = (5, 18),
    ):
        """
        Get closest schools to this output area, per age group
        (different schools admit pupils with different age ranges)

        Parameters
        ----------
        schools: 
            instance of Schools, with information on all schools in world.
        area:
            instance of Area.
        config:
            config dictionary.
        """
        self.schools = schools
        self.neighbour_schools = neighbour_schools
        self.school_age_range = age_range
        self.mandatory_school_age_range = mandatory_age_range
        self.education_sector_label = education_sector_label

    @classmethod
    def from_file(
            cls,
            schools: "Schools",
            config_filename: str = default_config_filename,
            # mandatory_age_range: Tuple[int, int] = (5, 18),#part of config ?
    ) -> "SchoolDistributor":
        """
        Initialize SchoolDistributor from path to its config file 

        Parameters
        ----------
        schools: 
            instance of Schools, with information on all schools in world.
        area:
            instance of Area.
        config:
            path to config dictionary

        Returns
        -------
        SchoolDistributor instance
        """
        with open(config_filename) as f:
            config = yaml.load(f, Loader=yaml.FullLoader)
        education_sector_label = SchoolDistributor.find_jobs(config)
        return SchoolDistributor(
            schools,
            education_sector_label,
            config["neighbour_schools"],
            config["age_range"],
            config["mandatory_age_range"],
        )

    @classmethod
    def from_geography(
            cls, geography: Geography, config_filename: str = default_config_filename
    ):
        return cls.from_file(geography.schools, config_filename)

    @staticmethod
    def find_jobs(config: dict):
        education_sector_label = []
        for value1 in config.values():
            if isinstance(value1, dict):
                for value2 in value1.values():
                    education_sector_label.append(value2["sector_id"])
        return education_sector_label

    def distribute_kids_to_school(self, areas: List[Area]):
        """
        Function to distribute kids to schools according to distance 
        """
        for area in areas:
            closest_schools_by_age = {}
            is_school_full = {}
            for agegroup in self.schools.school_trees:
                closest_schools = []
                closest_schools_idx = self.schools.get_closest_schools(
                    agegroup, area.coordinates, self.neighbour_schools,
                )
                for idx in closest_schools_idx:
                    real_idx = self.schools.school_agegroup_to_global_indices[agegroup][
                        idx
                    ]
                    closest_schools.append(self.schools.members[real_idx])
                closest_schools_by_age[agegroup] = closest_schools
                is_school_full[agegroup] = False
            self.distribute_mandatory_kids_to_school(
                area, is_school_full, closest_schools_by_age
            )
            self.distribute_non_mandatory_kids_to_school(
                area, is_school_full, closest_schools_by_age
            )

    def distribute_mandatory_kids_to_school(
            self, area: Area, is_school_full: dict, closest_schools_by_age: dict
    ):
        """
        Send kids to the nearest school among the self.neighbour_schools,
        that has vacancies. If none of them has vacancies, pick one of them
        at random (making it larger than it should be)
        """
        for person in area.people:
            if (
                    person.age <= self.mandatory_school_age_range[1]
                    and person.age >= self.mandatory_school_age_range[0]
            ):
                if person.age not in is_school_full:
                    continue
                if is_school_full[person.age]:
                    random_number = np.random.randint(
                        0,
                        min(
                            len(closest_schools_by_age[person.age]),
                            self.neighbour_schools,
                        ),
                    )
                    school = closest_schools_by_age[person.age][random_number]
                else:
                    schools_full = 0
                    for i in range(self.neighbour_schools):  # look for non full school
                        if i >= len(closest_schools_by_age[person.age]):
                            break
                        school = closest_schools_by_age[person.age][i]
                        if school.n_pupils >= school.n_pupils_max:
                            schools_full += 1
                        else:
                            break

                        is_school_full[person.age] = True
                        random_number = np.random.randint(
                            0,
                            min(
                                len(closest_schools_by_age[person.age]),
                                self.neighbour_schools,
                            ),
                        )
                        school = closest_schools_by_age[person.age][random_number]
                    else:  # just keep the school saved in the previous for loop
                        pass
                school.add(person, school.SubgroupType.students)

    def distribute_non_mandatory_kids_to_school(
            self, area: Area, is_school_full: dict, closest_schools_by_age: dict
    ):
        """
        For kids in age ranges that might go to school, but it is not mandatory
        send them to the closest school that has vacancies among the self.max_schools closests.
        If none of them has vacancies do not send them to school
        """
        for person in area.people:
            if (
                    self.school_age_range[0]
                    < person.age
                    < self.mandatory_school_age_range[0]
                    or self.mandatory_school_age_range[1]
                    < person.age
                    < self.school_age_range[1]
            ):
                if person.age not in is_school_full or is_school_full[person.age]:
                    continue
                else:
                    schools_full = 0
                    for i in range(self.neighbour_schools):  # look for non full school
                        if i >= len(closest_schools_by_age[person.age]):
                            # TEST THIS
                            break
                        school = closest_schools_by_age[person.age][i]
                        # check number of students in that age group
                        yearindex = person.age - school.age_min + 1
                        n_pupils_age = len(school.subgroups[yearindex].people)
                        if school.n_pupils >= school.n_pupils_max or n_pupils_age >= (
                                school.n_pupils_max / (school.age_max - school.age_min)
                        ):
                            schools_full += 1
                        else:
                            break
                school.add(person, school.SubgroupType.students)
                school.age_structure[person.age] += 1

    def distribute_teachers_to_schools_in_super_areas(
            self, super_areas: List[SuperArea]
    ):
        for msoarea in super_areas:
            self.distribute_teachers_to_school(msoarea)

    def distribute_teachers_to_school(self, msoarea: SuperArea):
        """
        Education sector
            2311: Higher education teaching professional
            2312: Further education teaching professionals
            2314: Secondary education teaching professionals
            2315: Primary and nursery education teaching professionals
            2316: Special needs education teaching professionals
        """
        # find people working in education
        # TODO add key-company-sector id to config.yaml
        teachers = [
            person
            for idx, person in enumerate(msoarea.workers)
            if person.sector == self.education_sector_label
        ]

        # equal chance to work in any school nearest to any area within msoa
        # Note: doing it this way rather then putting them into the area which
        # is currently chose in the for-loop in the world.py file ensure that
        # teachers are equally distr., no over-crowding
        areas_in_msoa = msoarea.areas
        areas_rv = stats.rv_discrete(
            values=(
                np.arange(len(areas_in_msoa)),
                np.array([1 / len(areas_in_msoa)] * len(areas_in_msoa)),
            )
        )
        areas_rnd_arr = areas_rv.rvs(size=len(teachers))

        for i, teacher in enumerate(teachers):
            if teacher.sub_sector != None:
                area = areas_in_msoa[areas_rnd_arr[i]]

                for school in area.schools:
                    if teacher.sub_sector in school.sector:
                        # (school.n_teachers < school.n_teachers_max) and \
                        school.add(teacher, school.SubgroupType.teacher)
                        school.n_teachers += 1
                    elif teacher.sub_sector == "special_needs":
                        # everyone has special needs :-)
                        # TODO fine better why for filtering
                        school.add(teacher, school.SubgroupType.teacher)
                        school.n_teachers += 1
