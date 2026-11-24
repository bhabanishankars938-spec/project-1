import math
import logging
from typing import Dict, Any, List, Optional, Tuple
from django.db.models import Q
from recruitment.models import (
    Job,
    Organization,
    Interview,
    State,
    District,
    City,
    Area,
    PinCode,
)

logger = logging.getLogger(__name__)


class LocationDiscoveryService:
    """
    HireNexa Geographic & Location Intelligence Service.
    Enables nearby job discovery, multi-tier area search, distance estimation (Haversine formula),
    office maps, and interview venue location discovery with privacy-preserving permissions.
    """

    @staticmethod
    def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculates great-circle distance between two GPS coordinates in kilometers.
        """
        r = 6371.0  # Earth's radius in kilometers
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        return round(r * c, 1)

    @classmethod
    def discover_nearby_jobs(
        cls,
        candidate_lat: Optional[float] = None,
        candidate_lon: Optional[float] = None,
        city_name: Optional[str] = None,
        state_name: Optional[str] = None,
        workplace_mode: Optional[str] = "ALL",  # ALL, REMOTE, HYBRID, ONSITE
        max_distance_km: float = 50.0,
        query: str = "",
        limit: int = 15,
    ) -> Dict[str, Any]:
        """
        Discovers jobs nearby candidate's location.
        Uses precise GPS distance calculation when coordinates are provided;
        falls back gracefully to structured city/state/pin matching or Remote mode.
        """
        jobs_qs = Job.objects.filter(is_active=True, status=Job.Status.ACTIVE).select_related("organization")

        if query:
            jobs_qs = jobs_qs.filter(
                Q(title__icontains=query) | Q(required_skills__icontains=query) | Q(company_name__icontains=query)
            )

        # Workplace mode filter
        if workplace_mode and workplace_mode != "ALL":
            if workplace_mode.upper() == "REMOTE":
                jobs_qs = jobs_qs.filter(workplace_type=Job.WorkplaceType.REMOTE)
            elif workplace_mode.upper() == "HYBRID":
                jobs_qs = jobs_qs.filter(workplace_type=Job.WorkplaceType.HYBRID)
            elif workplace_mode.upper() == "ONSITE":
                jobs_qs = jobs_qs.filter(workplace_type=Job.WorkplaceType.ONSITE)

        has_coordinates = candidate_lat is not None and candidate_lon is not None
        matched_jobs = []

        for job in jobs_qs:
            org = job.organization
            job_lat = float(org.latitude) if (org and org.latitude) else None
            job_lon = float(org.longitude) if (org and org.longitude) else None

            distance_km = None
            is_nearby = False
            match_type = "STANDARD"

            # 1. Coordinate Distance Check
            if has_coordinates and job_lat and job_lon:
                distance_km = cls.haversine_distance_km(candidate_lat, candidate_lon, job_lat, job_lon)
                if distance_km <= max_distance_km:
                    is_nearby = True
                    match_type = "GPS_PROXIMITY"
            # 2. Textual City/State match
            elif city_name and (
                city_name.lower() in (job.city or "").lower()
                or city_name.lower() in (job.location or "").lower()
                or (org and city_name.lower() in (org.city or "").lower())
            ):
                is_nearby = True
                match_type = "CITY_MATCH"
            elif state_name and (
                state_name.lower() in (job.state or "").lower()
                or (org and state_name.lower() in (org.state or "").lower())
            ):
                is_nearby = True
                match_type = "STATE_MATCH"
            elif job.workplace_type == Job.WorkplaceType.REMOTE:
                is_nearby = True
                match_type = "REMOTE_ANYWHERE"
            elif not city_name and not state_name and not has_coordinates:
                is_nearby = True
                match_type = "ALL_LOCATIONS"

            if is_nearby:
                office_address = ""
                if org:
                    parts = [org.building_name, org.street_address, org.area, org.city, org.state, org.pin_code]
                    office_address = ", ".join([p for p in parts if p])

                matched_jobs.append({
                    "job_id": job.id,
                    "title": job.title,
                    "company_name": job.company_name,
                    "location_label": job.location or (org.city if org else "India"),
                    "city": job.city or (org.city if org else ""),
                    "state": job.state or (org.state if org else ""),
                    "workplace_type": job.get_workplace_type_display(),
                    "distance_km": distance_km,
                    "distance_label": f"{distance_km} km away" if distance_km is not None else ("Remote" if job.workplace_type == Job.WorkplaceType.REMOTE else "City Area"),
                    "match_type": match_type,
                    "latitude": job_lat,
                    "longitude": job_lon,
                    "office_address": office_address or job.office_address,
                    "vacancies": job.vacancies,
                    "apply_url": f"/jobs/{job.id}/",
                })

        # Sort: GPS nearest first, then city matches, then remote
        matched_jobs.sort(
            key=lambda x: (
                0 if x["distance_km"] is not None else (1 if x["match_type"] == "CITY_MATCH" else 2),
                x["distance_km"] if x["distance_km"] is not None else 9999,
            )
        )

        return {
            "search_params": {
                "has_coordinates": has_coordinates,
                "city": city_name or "",
                "state": state_name or "",
                "workplace_mode": workplace_mode,
                "max_distance_km": max_distance_km,
            },
            "total_found": len(matched_jobs),
            "jobs": matched_jobs[:limit],
        }

    @classmethod
    def get_company_office_map(cls, org_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves verified corporate office coordinates and structured address for map rendering."""
        org = Organization.objects.filter(id=org_id).first()
        if not org:
            return None

        has_coords = bool(org.latitude and org.longitude)
        return {
            "org_id": org.id,
            "company_name": org.name,
            "building_name": org.building_name,
            "street_address": org.street_address,
            "area": org.area,
            "city": org.city,
            "state": org.state,
            "pin_code": org.pin_code,
            "formatted_address": org.formatted_address or f"{org.building_name}, {org.city}, {org.state} - {org.pin_code}".strip(", -"),
            "latitude": float(org.latitude) if has_coords else None,
            "longitude": float(org.longitude) if has_coords else None,
            "has_coordinates": has_coords,
        }

    @classmethod
    def get_interview_venue_info(cls, interview_id: int) -> Optional[Dict[str, Any]]:
        """Retrieves interview venue and physical instructions when interview mode is IN_PERSON."""
        interview = Interview.objects.filter(id=interview_id).select_related("application__job__organization").first()
        if not interview:
            return None

        job = interview.application.job
        org = job.organization

        is_in_person = interview.mode == Interview.Mode.IN_PERSON
        return {
            "interview_id": interview.id,
            "round_name": interview.round_name,
            "scheduled_at": interview.scheduled_at.strftime("%B %d, %Y at %I:%M %p"),
            "mode": interview.get_mode_display(),
            "is_in_person": is_in_person,
            "meeting_link": interview.meeting_link if not is_in_person else "",
            "venue_location": interview.location or (org.formatted_address if org else job.location),
            "notes": interview.notes,
        }
