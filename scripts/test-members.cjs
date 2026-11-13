const {test} = require('node:test');
const assert = require('node:assert/strict');
const directory = require('../lab-preview/members.js');
const member = (id, enrollmentYear, graduationYear, extra={}) => ({id,name:id,role:'student',enrollmentYear,graduationYear,...extra});

test('graduation follows the calendar year without a manual status flag', () => {
 const person=member('student',2021,2024);
 assert.equal(directory.status(person,2023),'student');
 assert.equal(directory.status(person,2024),'alumni');
 assert.equal(directory.status(person,2025),'alumni');
 assert.equal(directory.status({...person,role:'advisor'},2025),'advisor');
});
test('null years and future enrollment stay distinct from alumni', () => {
 assert.equal(directory.status(member('unknown',null,null),2026),'student');
 assert.equal(directory.status(member('current',2025,null),2026),'student');
 assert.equal(directory.status(member('incoming',2027,2030),2026),'incoming');
 assert.equal(directory.status(member('incoming',2027,2030),2027),'student');
});
test('current students group by enrollment, alumni by graduation, unknown last', () => {
 const roster=[member('b',2024,2028),member('a',2024,null),member('old',2020,2024),member('unknown',null,null),member('newer',2025,2029)];
 const result=directory.groups(roster,2026);
 assert.deepEqual(result.students.map(g=>g.year),[2025,2024,null]);
 assert.deepEqual(result.students[1].members.map(m=>m.id),['a','b']);
 assert.deepEqual(result.alumni.map(g=>g.year),[2024]);
 assert.equal(result.students.reduce((n,g)=>n+g.members.length,0)+result.alumni[0].members.length,roster.length);
});
test('the year rollover uses the lab timezone', () => {
 assert.equal(directory.currentYear(new Date('2026-12-31T15:59:59Z')),2026);
 assert.equal(directory.currentYear(new Date('2026-12-31T16:00:00Z')),2027);
});
test('inferred years are visibly qualified', () => {
 assert.equal(directory.years(member('a',2022,2026,{yearEvidence:{status:'inferred'}}),2026),'≈ 2022–2026');
 assert.equal(directory.years(member('a',2022,null),2026),'2022–present');
 assert.equal(directory.years(member('a',null,null),2026),'Years not listed');
});
