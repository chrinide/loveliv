#coding=utf-8

from . import traditional, score_match, score_match_legacy, medley_festival

parsers={
    'traditional': traditional.parse_score,
    'score_match_old': score_match_legacy.parse_score,
    'score_match': score_match.parse_score,
    'medley_fes': medley_festival.parse_score,
}
