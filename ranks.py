
r_dict = {
    'Vanemveteran': [3000, 5000],
    'Veteran': [500, 2999],
    'Kindral': [450, 499],
    'Brigadir': [400, 449],
    'Kolonel': [350, 399],
    'Kolonelleitnant': [300, 349],
    'Major': [250, 299],
    'Kapten': [200, 249],
    'Vanemleitnant': [150, 199],
    'Nooremleitnant': [100, 149],
    'Voliohvitser': [50, 99],
    'Seersantmajor': [45, 49],
    'Seersant': [25, 44],
    'Kapral': [5, 24],
    'Reamees': [1, 4],
}

def getRankNameFromCareerRank(userCareerRank : int) -> str:
    for rank_name, (min_val, max_val) in r_dict.items():
        if min_val <= userCareerRank <= max_val:
            return rank_name
    return None
