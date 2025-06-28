import http from 'k6/http';
import { sleep, check } from 'k6';

export let options = {
    vus: 50,            // Virtual users
    duration: '1m',     // Test duration
    thresholds: {
        http_req_duration: ['p(95)<500'], // 95% of requests under 500ms
        http_req_failed: ['rate<0.01'],    // Fail rate < 1%
    },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_PREFIX = '/api/v1';

export default function () {
    // Health check
    let health = http.get(`${BASE_URL}/health`);
    check(health, {
        'health status 200': (r) => r.status === 200,
    });

    // AI mentor conversation
    let payload = JSON.stringify({ message: 'How do I solve this problem?', context: {} });
    let res = http.post(
        `${BASE_URL}${API_PREFIX}/ai/mentor/conversation`,
        payload,
        { headers: { 'Content-Type': 'application/json' } }
    );
    check(res, {
        'mentor conv 200': (r) => r.status === 200,
        'mentor conv has response': (r) => r.json().response !== undefined,
    });

    // Engagement analysis
    let analysisPayload = JSON.stringify({ user_id: 1, action: 'test', metadata: {}, user_message: 'I need help' });
    let eng = http.post(
        `${BASE_URL}${API_PREFIX}/ai/engagement/analyze`,
        analysisPayload,
        { headers: { 'Content-Type': 'application/json' } }
    );
    check(eng, {
        'engage analyze 200': (r) => r.status === 200,
    });

    sleep(1);
}
