import os
from pathlib import Path

import pytest
import numpy as np
import pandas as pd
from collections import defaultdict

from june import paths
from june.demography.geography import Geography, Area
from june.demography import Person
from june.groups.company import Company, Companies

default_data_path = paths.data_path / "processed/census_data/company_data/"
default_size_nr_file = default_data_path / "companysize_msoa11cd_2019.csv"
default_sector_nr_per_msoa_file = default_data_path / "companysector_msoa11cd_2011.csv"


@pytest.fixture(name="super_area_companies", scope="module")
def create_super_area():
    g = Geography.from_file(
        filter_key={"msoa" : ["E02002559"]},
    )
    return g.super_areas.members[0]

@pytest.fixture(name="person")
def create_person():
    return Person(sex="m", age=44)


class TestCompany:
    @pytest.fixture(name="company")
    def create_company(self, super_area_companies):
        return Company(
            super_area = super_area_companies,
            n_workers_max = 115,
            sector = "Q",
        )
    
    def test__company_grouptype(self, company):
        assert company.SubgroupType.workers == 0

    def test__empty_company(self, company):
        assert len(company.people) == 0
    
    def test__filling_company(self, person, company):
        company.add(person)
        assert list(company.people)[0] == person

    def test__person_is_employed(self, person, company):
        company.add(person)
        persons_primary_activity = person.subgroups[
            person.ActivityType.primary_activity
        ]
        company_workers = company.subgroups[Company.SubgroupType.workers]
        assert persons_primary_activity == company_workers


class TestCompanies:
    @pytest.fixture(name="module_companies", scope="module")
    def create_companies(self, super_area_companies):
        companies = Companies.for_super_areas(
            [super_area_companies],
            default_size_nr_file,
            default_sector_nr_per_msoa_file,
        )
        return companies

    def test__company_size_distr(self, module_companies):
        assert len(module_companies) == 610
        sizes_dict = defaultdict(int)
        bins = [0, 10, 20, 50, 100, 250, 500, 1000, 1500]
        for company in module_companies:
            size = company.n_workers_max
            idx = np.searchsorted(bins, size) - 1
            sizes_dict[idx] += 1
        assert np.isclose(sizes_dict[0], 505, atol=10)
        assert np.isclose(sizes_dict[1], 40, atol=10)
        assert np.isclose(sizes_dict[2], 40, atol=10)
        assert np.isclose(sizes_dict[3], 10, atol=5)
        assert np.isclose(sizes_dict[4], 10, atol=5)

    def test__companies_multiple_areas(self, ):
        g = Geography.from_file(filter_key={"msoa" : ["E02002559", "E02000001"]})
        companies = Companies.for_geography(g)
