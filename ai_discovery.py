"""Local AI reminder discovery; hiding never deletes saved references or counts."""
import time
import uuid

MONTH_MS = 30 * 86400 * 1000


def milliseconds(value):
    if not isinstance(value, (int, float)):
        return 0
    return int(value if value > 100_000_000_000 else value * 1000)


class AIDiscovery:
    def __init__(self, provider, interval=30):
        self.provider = provider
        self.interval = interval
        self.last_scan = -float('inf')
        self.threads = []

    def reconcile(self, cards, now_ms):
        now = time.monotonic()
        if now - self.last_scan >= self.interval:
            self.threads = self.provider()
            self.last_scan = now
        changed = False
        indexed = {c.get('codexThreadId'): c for c in reversed(cards)
                   if c.get('codexThreadId') and c.get('codexHost', 'local') == 'local'}
        for thread in self.threads:
            identifier = thread.get('id')
            activity = milliseconds(thread.get('updatedAt'))
            if not identifier or thread.get('hostId', 'local') != 'local' or not activity:
                continue
            card = indexed.get(identifier)
            if card is None:
                if now_ms - activity > MONTH_MS:
                    continue
                card = {'id': str(uuid.uuid4()), 'title': (thread.get('name') or 'AI 对话')[:80],
                        'tag': '', 'intervalMs': 1800000, 'createdAt': now_ms,
                        'intervalValue': 30, 'intervalUnit': 'minute',
                        'nextAt': None, 'started': False, 'codexThreadId': identifier,
                        'codexHost': 'local', 'codexArmed': False, 'codexDue': False}
                cards.append(card)
                indexed[identifier] = card
                changed = True
            values = {'aiManaged': True, 'aiLastActivityAt': max(activity, card.get('aiLastActivityAt') or 0),
                      'codexThreadName': thread.get('name') or card.get('codexThreadName') or 'AI 对话'}
            for key, value in values.items():
                if card.get(key) != value:
                    card[key] = value
                    changed = True
        for card in cards:
            if not card.get('codexThreadId') or card.get('codexHost', 'local') != 'local':
                continue
            activity = max(card.get('aiLastActivityAt') or 0, milliseconds(card.get('codexLatestCompletedAt')))
            if not activity:
                activity = milliseconds(card.get('createdAt'))
            if not activity:
                continue  # Missing metadata is not proof that a conversation expired.
            hidden = now_ms - activity > MONTH_MS
            canonical = indexed.get(card['codexThreadId'])
            if canonical is not None and canonical is not card:
                hidden = True  # Keep duplicate references/counts, show one reminder.
            if card.get('aiHidden', False) != hidden:
                card['aiHidden'] = hidden
                changed = True
        return changed
