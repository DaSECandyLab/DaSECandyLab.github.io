/* Derive membership from years; there is no separately maintained alumni flag. */
(function (root) {
  'use strict';
  function currentYear(date = new Date()) {
    return Number(new Intl.DateTimeFormat('en', {year: 'numeric', timeZone: 'Asia/Shanghai'}).format(date));
  }
  function status(member, year = currentYear()) {
    if (member.role === 'advisor') return 'advisor';
    if (member.enrollmentYear != null && member.enrollmentYear > year) return 'incoming';
    if (member.graduationYear != null && member.graduationYear <= year) return 'alumni';
    return 'student';
  }
  function groups(members, year = currentYear()) {
    const sections = {advisor: [], student: [], alumni: [], incoming: []};
    members.forEach(member => sections[status(member, year)].push(member));
    function cohorts(list, key) {
      const buckets = new Map();
      list.forEach(member => {
        const cohort = member[key] ?? null;
        if (!buckets.has(cohort)) buckets.set(cohort, []);
        buckets.get(cohort).push(member);
      });
      return [...buckets].sort(([a], [b]) => a === null ? 1 : b === null ? -1 : b - a)
        .map(([year, members]) => ({year, members: members.sort((a, b) => a.name.localeCompare(b.name, 'en'))}));
    }
    return {advisors: sections.advisor.sort((a, b) => a.name.localeCompare(b.name, 'en')),
      students: cohorts(sections.student, 'enrollmentYear'),
      alumni: cohorts(sections.alumni, 'graduationYear'),
      incoming: cohorts(sections.incoming, 'enrollmentYear')};
  }
  function years(member, year = currentYear()) {
    const start = member.enrollmentYear, end = member.graduationYear;
    let text = start != null ? `${start}–${end ?? 'present'}` : end != null ? `Graduated ${end}` : 'Years not listed';
    if (start != null && end == null && start > year) text = `Enrolling ${start}`;
    return (member.yearEvidence?.status === 'inferred' && (start != null || end != null) ? '≈ ' : '') + text;
  }
  const api = {currentYear, status, groups, years};
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.MemberDirectory = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
