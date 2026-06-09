from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urlparse

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Candidate, Job, JobCandidate


@dataclass(frozen=True)
class CandidateLead:
    name: str | None
    current_company: str | None
    title: str | None
    location: str | None
    email: str | None
    github_url: str | None
    linkedin_url: str | None
    homepage_url: str | None
    source_platform: str | None
    source_url: str | None
    evidence: list[str]
    skills: list[str]
    matched_keywords: list[str]
    confidence: float
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class NormalizationResult:
    accepted: bool
    lead: CandidateLead | None
    reasons: list[str] = field(default_factory=list)


LEAD_COLLECTION_KEYS = {
    "candidate_leads",
    "candidateLeads",
    "leads",
    "candidates",
    "候选人线索",
    "候选人",
}
LIVE_RESULT_CONTAINER_KEYS = {"实时检索", "live_search", "liveSearch"}
LIVE_RESULT_KEYS = {"results", "items", "records"}
URL_FIELDS = ("source_url", "sourceUrl", "profile_url", "profileUrl", "url", "html_url", "htmlUrl", "link")
STRING_LIMITS = {
    "name": 128,
    "current_company": 128,
    "title": 128,
    "location": 128,
    "email": 256,
    "github_url": 512,
    "linkedin_url": 512,
    "homepage_url": 512,
    "source_platform": 64,
    "source_url": 512,
}


def normalize_candidate_lead(raw: Mapping[str, Any]) -> NormalizationResult:
    payload = dict(raw)
    evidence = _string_list(
        _first_present(payload, ("evidence", "evidences", "evidence_items", "evidenceItems", "证据", "snippet", "description"))
    )
    skills = _string_list(_first_present(payload, ("skills", "skill_tags", "skillTags", "topics", "tags", "能力")))
    matched_keywords = _string_list(
        _first_present(payload, ("matched_keywords", "matchedKeywords", "keywords", "search_keywords", "搜索关键词"))
    )
    if not skills and matched_keywords:
        skills = matched_keywords[:]
    if not matched_keywords and skills:
        matched_keywords = skills[:]

    source_url = _clean_url(_first_present(payload, URL_FIELDS))
    github_url = _clean_url(_first_present(payload, ("github_url", "githubUrl")))
    linkedin_url = _clean_url(_first_present(payload, ("linkedin_url", "linkedinUrl")))
    homepage_url = _clean_url(_first_present(payload, ("homepage_url", "homepageUrl", "website", "blog_url", "blogUrl")))
    if not github_url and source_url and _is_domain(source_url, "github.com"):
        github_url = _github_profile_url_from_url(source_url) or source_url
    if not linkedin_url and source_url and _is_domain(source_url, "linkedin.com"):
        linkedin_url = source_url
    if not homepage_url and source_url and not github_url and not linkedin_url:
        homepage_url = source_url

    lead = CandidateLead(
        name=_clean_string(_first_present(payload, ("name", "candidate_name", "candidateName", "姓名", "owner_login", "author")), "name"),
        current_company=_clean_string(
            _first_present(payload, ("current_company", "currentCompany", "company", "organization", "institution", "affiliation", "当前公司")),
            "current_company",
        ),
        title=_clean_string(_first_present(payload, ("title", "job_title", "jobTitle", "headline", "position", "职位")), "title"),
        location=_clean_string(_first_present(payload, ("location", "city", "地区", "城市")), "location"),
        email=_clean_email(_first_present(payload, ("email", "邮箱"))),
        github_url=github_url,
        linkedin_url=linkedin_url,
        homepage_url=homepage_url,
        source_platform=_clean_string(
            _first_present(payload, ("source_platform", "sourcePlatform", "source_key", "sourceKey", "platform", "source_name")),
            "source_platform",
        ),
        source_url=source_url or github_url or linkedin_url or homepage_url,
        evidence=evidence,
        skills=skills,
        matched_keywords=matched_keywords,
        confidence=_confidence(_first_present(payload, ("confidence", "score", "match_score", "matchScore"))),
        raw_payload=payload,
    )

    reasons: list[str] = []
    if not lead.name and not (lead.source_url or lead.github_url or lead.linkedin_url or lead.homepage_url):
        reasons.append("name or profile_url/source_url is required")
    if not lead.source_platform:
        reasons.append("source_platform is required")
    if not lead.source_url and not lead.evidence:
        reasons.append("source_url or evidence is required")
    return NormalizationResult(accepted=not reasons, lead=lead if not reasons else None, reasons=reasons)


def extract_candidate_leads(payload: Any) -> list[dict[str, Any]]:
    leads: list[dict[str, Any]] = []
    seen_structured_ids: set[int] = set()

    def visit(value: Any, parent_key: str | None = None) -> None:
        if isinstance(value, list):
            if parent_key in LEAD_COLLECTION_KEYS:
                for item in value:
                    if isinstance(item, Mapping):
                        marker = id(item)
                        if marker not in seen_structured_ids:
                            seen_structured_ids.add(marker)
                            leads.append(dict(item))
                return
            for item in value:
                visit(item, parent_key)
            return

        if not isinstance(value, Mapping):
            return

        for key, child in value.items():
            if key in LIVE_RESULT_CONTAINER_KEYS and isinstance(child, Mapping):
                for result_key in LIVE_RESULT_KEYS:
                    results = child.get(result_key)
                    if isinstance(results, list):
                        for item in results:
                            if isinstance(item, Mapping):
                                leads.append(_lead_from_search_result(item))
                continue
            visit(child, str(key))

    visit(payload)
    return leads


def empty_lead_ingestion_result(source_task_id: str, reason: str | None = None) -> dict[str, Any]:
    result = {
        "found": 0,
        "normalized": 0,
        "inserted_candidates": 0,
        "updated_candidates": 0,
        "linked_job_candidates": 0,
        "duplicates": 0,
        "rejected": 0,
        "rejected_reasons": {},
        "source_task_id": source_task_id,
    }
    if reason:
        result["rejected"] = 1
        result["rejected_reasons"] = {reason: 1}
    return result


def ingest_candidate_leads(
    session: Session,
    *,
    project_id: str,
    job_id: str,
    source_task_id: str,
    raw_leads: list[Mapping[str, Any]],
) -> dict[str, Any]:
    result = empty_lead_ingestion_result(source_task_id)
    result["found"] = len(raw_leads)

    job = session.get(Job, job_id)
    if job is None or job.project_id != project_id:
        result["rejected"] = len(raw_leads) or 1
        result["rejected_reasons"] = {"job not found for project": result["rejected"]}
        return result

    seen_keys: set[tuple[str, ...]] = set()
    for raw in raw_leads:
        normalized = normalize_candidate_lead(raw)
        if not normalized.accepted or normalized.lead is None:
            result["rejected"] += 1
            _record_rejected_reasons(result, normalized.reasons)
            continue

        lead = normalized.lead
        result["normalized"] += 1
        duplicate_keys = _dedupe_keys(lead)
        if duplicate_keys and any(key in seen_keys for key in duplicate_keys):
            result["duplicates"] += 1
            continue
        seen_keys.update(duplicate_keys)

        candidate = _find_existing_candidate(session, lead)
        candidate_was_existing = candidate is not None
        if candidate is None:
            candidate = _new_candidate(lead, source_task_id)
            session.add(candidate)
            session.flush()
            result["inserted_candidates"] += 1
        else:
            changed = _merge_candidate(candidate, lead)
            if changed:
                result["updated_candidates"] += 1

        link = session.scalar(
            select(JobCandidate).where(
                JobCandidate.job_id == job_id,
                JobCandidate.candidate_id == candidate.id,
            )
        )
        if link is None:
            session.add(
                JobCandidate(
                    project_id=project_id,
                    job_id=job_id,
                    candidate_id=candidate.id,
                    match_score=_match_score(lead.confidence),
                    pipeline_status="sourced",
                    evidence=list(lead.evidence),
                    source_task_id=source_task_id,
                )
            )
            result["linked_job_candidates"] += 1
        else:
            _merge_job_candidate_link(link, project_id, lead.evidence, source_task_id)
            if candidate_was_existing:
                result["duplicates"] += 1

    session.commit()
    return result


def _lead_from_search_result(result: Mapping[str, Any]) -> dict[str, Any]:
    url = _clean_url(_first_present(result, URL_FIELDS))
    owner_login = _clean_string(result.get("owner_login") or result.get("author"), "name")
    evidence = _string_list([result.get("title"), result.get("snippet") or result.get("description")])
    skills = _string_list(result.get("topics") or result.get("tags") or result.get("matched_keywords"))
    lead = {
        "name": owner_login or _name_from_title(result.get("title")),
        "current_company": _first_present(result, ("company", "organization", "institution", "affiliation", "lab")),
        "title": result.get("title"),
        "location": result.get("location"),
        "email": result.get("email"),
        "source_platform": result.get("source_key") or result.get("source_platform") or result.get("source_name") or "search_result",
        "source_url": url,
        "evidence": evidence,
        "skills": skills,
        "matched_keywords": skills,
        "confidence": result.get("confidence") or _confidence_from_rank(result.get("rank")),
        "raw_payload": dict(result),
    }
    if url and _is_domain(url, "github.com"):
        lead["github_url"] = _github_profile_url_from_url(url) or url
    elif url and _is_domain(url, "linkedin.com"):
        lead["linkedin_url"] = url
    elif url:
        lead["homepage_url"] = url
    return lead


def _record_rejected_reasons(result: dict[str, Any], reasons: list[str]) -> None:
    rejected_reasons = result.setdefault("rejected_reasons", {})
    for reason in reasons:
        rejected_reasons[reason] = int(rejected_reasons.get(reason, 0)) + 1


def _find_existing_candidate(session: Session, lead: CandidateLead) -> Candidate | None:
    if lead.email:
        candidate = session.scalar(select(Candidate).where(func.lower(Candidate.email) == lead.email.casefold()))
        if candidate:
            return candidate
    for field_name, value in (
        ("github_url", lead.github_url),
        ("linkedin_url", lead.linkedin_url),
        ("homepage_url", lead.homepage_url),
    ):
        if value:
            candidate = session.scalar(select(Candidate).where(getattr(Candidate, field_name) == value))
            if candidate:
                return candidate
    if lead.name and lead.current_company:
        candidate = session.scalar(
            select(Candidate).where(
                func.lower(Candidate.name) == lead.name.casefold(),
                func.lower(Candidate.current_company) == lead.current_company.casefold(),
            )
        )
        if candidate:
            return candidate
    if lead.name and lead.source_platform and lead.source_url:
        candidate = session.scalar(
            select(Candidate).where(
                func.lower(Candidate.name) == lead.name.casefold(),
                Candidate.source_platform == lead.source_platform,
                Candidate.source_url == lead.source_url,
            )
        )
        if candidate:
            return candidate
    return None


def _new_candidate(lead: CandidateLead, source_task_id: str) -> Candidate:
    name = lead.name or _display_name_from_url(lead.source_url or lead.github_url or lead.linkedin_url or lead.homepage_url) or "Unknown Candidate"
    return Candidate(
        id=_candidate_id(lead),
        name=_clean_string(name, "name") or "Unknown Candidate",
        title=lead.title,
        current_company=lead.current_company,
        location=lead.location,
        city=lead.location,
        email=lead.email,
        github_url=lead.github_url,
        linkedin_url=lead.linkedin_url,
        homepage_url=lead.homepage_url,
        source_platform=lead.source_platform,
        source_url=lead.source_url,
        evidence=list(lead.evidence),
        skills=list(lead.skills),
        created_from_task_id=source_task_id,
        raw_payload=lead.raw_payload,
    )


def _merge_candidate(candidate: Candidate, lead: CandidateLead) -> bool:
    changed = False
    for field_name, value in (
        ("title", lead.title),
        ("current_company", lead.current_company),
        ("location", lead.location),
        ("city", lead.location),
        ("email", lead.email),
        ("github_url", lead.github_url),
        ("linkedin_url", lead.linkedin_url),
        ("homepage_url", lead.homepage_url),
        ("source_platform", lead.source_platform),
        ("source_url", lead.source_url),
        ("raw_payload", lead.raw_payload),
    ):
        if value and not getattr(candidate, field_name, None):
            setattr(candidate, field_name, value)
            changed = True
    merged_evidence = _merge_lists(candidate.evidence, lead.evidence)
    if merged_evidence != (candidate.evidence or []):
        candidate.evidence = merged_evidence
        changed = True
    merged_skills = _merge_lists(candidate.skills, lead.skills)
    if merged_skills != (candidate.skills or []):
        candidate.skills = merged_skills
        changed = True
    return changed


def _merge_job_candidate_link(link: JobCandidate, project_id: str, evidence: list[str], source_task_id: str) -> bool:
    changed = False
    if not link.project_id:
        link.project_id = project_id
        changed = True
    if source_task_id and link.source_task_id != source_task_id:
        link.source_task_id = source_task_id
        changed = True
    merged_evidence = _merge_lists(link.evidence, evidence)
    if merged_evidence != (link.evidence or []):
        link.evidence = merged_evidence
        changed = True
    return changed


def _dedupe_keys(lead: CandidateLead) -> list[tuple[str, ...]]:
    keys: list[tuple[str, ...]] = []
    if lead.email:
        keys.append(("email", lead.email.casefold()))
    for key_name, value in (
        ("github_url", lead.github_url),
        ("linkedin_url", lead.linkedin_url),
        ("homepage_url", lead.homepage_url),
    ):
        if value:
            keys.append((key_name, _normalize_url(value)))
    if lead.name and lead.current_company:
        keys.append(("name_company", lead.name.casefold(), lead.current_company.casefold()))
    if lead.name and lead.source_platform and lead.source_url:
        keys.append(("name_source", lead.name.casefold(), lead.source_platform.casefold(), _normalize_url(lead.source_url)))
    return keys


def _candidate_id(lead: CandidateLead) -> str:
    stable = "|".join(":".join(key) for key in _dedupe_keys(lead)) or repr(sorted(lead.raw_payload.items()))
    digest = hashlib.sha1(stable.encode("utf-8")).hexdigest()[:16]
    return f"cand_lead_{digest}"


def _match_score(confidence: float) -> int:
    return max(0, min(100, round(confidence * 100)))


def _confidence(value: Any) -> float:
    if value is None or value == "":
        return 0.58
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.58
    if number > 1:
        number = number / 100
    return max(0.0, min(1.0, round(number, 3)))


def _confidence_from_rank(rank: Any) -> float:
    try:
        rank_number = int(rank)
    except (TypeError, ValueError):
        return 0.62
    return max(0.45, min(0.86, round(0.86 - max(0, rank_number - 1) * 0.06, 2)))


def _first_present(payload: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _string_list(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    if isinstance(value, str):
        return [_squash(value)] if _squash(value) else []
    if isinstance(value, Mapping):
        text = value.get("summary") or value.get("text") or value.get("title") or value.get("url")
        return [_squash(text)] if _squash(text) else []
    if isinstance(value, list | tuple | set):
        merged: list[str] = []
        for item in value:
            merged.extend(_string_list(item))
        return _unique_strings(merged)
    return [_squash(value)] if _squash(value) else []


def _merge_lists(existing: list[str] | None, incoming: list[str]) -> list[str]:
    return _unique_strings([*(existing or []), *incoming])


def _unique_strings(values: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _squash(value)
        key = cleaned.casefold()
        if not cleaned or key in seen:
            continue
        seen.add(key)
        unique.append(cleaned[:700])
    return unique[:20]


def _clean_string(value: Any, field_name: str) -> str | None:
    text = _squash(value)
    if not text:
        return None
    return text[: STRING_LIMITS[field_name]]


def _clean_email(value: Any) -> str | None:
    text = _squash(value).casefold()
    if not text or "@" not in text:
        return None
    return text[: STRING_LIMITS["email"]]


def _clean_url(value: Any) -> str | None:
    text = _squash(value)
    if not text:
        return None
    if text.startswith("www."):
        text = f"https://{text}"
    if not text.startswith(("http://", "https://")):
        return None
    return text[:512]


def _normalize_url(value: str) -> str:
    return value.rstrip("/").casefold()


def _squash(value: Any) -> str:
    text = str(value or "").strip()
    return re.sub(r"\s+", " ", text)


def _is_domain(url: str, domain: str) -> bool:
    host = urlparse(url).netloc.casefold().removeprefix("www.")
    return host == domain or host.endswith(f".{domain}")


def _github_profile_url_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None
    owner = parts[0]
    if owner in {"orgs", "topics", "marketplace", "features", "collections"}:
        return None
    return f"https://github.com/{owner}"


def _display_name_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    if parts:
        return parts[-1].replace("-", " ").replace("_", " ").title()
    host = parsed.netloc.removeprefix("www.")
    return host.split(".")[0].replace("-", " ").title() if host else None


def _name_from_title(value: Any) -> str | None:
    text = _squash(value)
    if not text:
        return None
    first = re.split(r"[:|/,-]", text, maxsplit=1)[0].strip()
    if len(first.split()) > 5:
        return None
    return first[:128] or None
