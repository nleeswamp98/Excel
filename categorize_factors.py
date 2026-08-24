import sqlite3
import config
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# =============================================================================
#  CONFIGURATION — adjust everything here before running
# =============================================================================

RUN_MODE = "production"        # "production" = normal categorization
                               # "interactive" = sandbox for tuning/testing

THRESHOLD = 0.12               # minimum cosine similarity score to accept a match
                               # lower = more lenient, higher = stricter
                               # typical range: 0.05 (very loose) to 0.40 (very tight)

TOPIC_NAME_WEIGHT = 6          # how many times to repeat the topic name vs factor text
                               # 1 = equal footing, 6 = name-heavy, 10+ = name dominates

INCLUDE_ALREADY_CATEGORIZED = True   # True = re-evaluate ALL topics including ones that already have a category assigned
                                      # False = only process uncategorized topics

DRY_RUN = True                 # only applies to interactive mode
                               # True  = preview results, no DB writes
                               # False = commit changes to database

SHOW_TOP_N_MATCHES = 3         # how many runner-up categories to display per topic
                               # in interactive mode (useful for tuning the concept map)

# =============================================================================
#  ENGINE — no need to edit below this line
# =============================================================================

def setup_categorization_engine():
    categories = list(config.TOPIC_CONCEPT_MAP.keys())
    documents = list(config.TOPIC_CONCEPT_MAP.values())

    vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 3))
    category_vectors = vectorizer.fit_transform(documents)

    return categories, vectorizer, category_vectors


def _build_topic_vector(vectorizer, topic_name, factor_text, weight):
    topic_name_str = topic_name or ""
    factor_text_str = factor_text or ""
    weighted_text = (topic_name_str + " ") * weight + factor_text_str
    normalized = weighted_text.lower().replace("-", " ")
    return vectorizer.transform([normalized])


def categorize_topics(threshold, topic_name_weight):
    print(f"Connecting to databse...")
    conn = sqlite3.connect(config.DATABASE_FILE)
    cursor = conn.cursor()

    print("Setting up categorization engine...")
    categories, vectorizer, category_vectors = setup_categorization_engine()

    sql_query = """
        SELECT
            t.label_id,
            t.label_name,
            f.factor_text
        FROM
            Property_Factor_Labels t
        JOIN
            Property_Factors f ON t.label_id = f.label_id
        WHERE
            t.category IS NULL OR t.category = ''
    """

    try:
        cursor.execute(sql_query)
        topics_to_categorize = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"Database error: {e}")
        conn.close()
        return

    if not topics_to_categorize:
        print("No new uncategorized topics found. All set.")
        conn.close()
        return

    print(f"Found {len(topics_to_categorize)} new uncategorized topics. Starting categorization...")

    updated_count = 0
    uncategorized_list = []

    for topic_id, topic_name, factor_text in topics_to_categorize:

        topic_vector = _build_topic_vector(vectorizer, topic_name, factor_text, topic_name_weight)
        scores = cosine_similarity(topic_vector, category_vectors)

        max_score = scores.max()
        best_match_index = scores.argmax()

        if max_score > threshold:
            found_category = categories[best_match_index]
            cursor.execute(
                "UPDATE Property_Factor_Labels SET category = ? WHERE label_id = ?",
                (found_category, topic_id)
            )
            #print(f"Categorized '{topic_name}' as '{found_category}'. Score: {max_score:.2f}")
            updated_count += 1
        else:
            uncategorized_list.append((topic_name, max_score))

    conn.commit()
    conn.close()

    print(f"\n---- Update complete ----")
    print(f"Successfully categorized {updated_count} new topics.")

    if uncategorized_list:
        sorted_uncategorized = sorted(uncategorized_list, key=lambda x: x[1], reverse=True)


def interactive_categorize(threshold, topic_name_weight, include_already_categorized, dry_run, top_n):

    mode_label = "DRY RUN (no DB writes)" if dry_run else "LIVE MODE (will update DB)"
    scope_label = "ALL topics (including already categorized)" if include_already_categorized else "Only uncategorized topics"

    print(f"\n{'='*60}")
    print(f"  INTERACTIVE CATEGORIZATION")
    print(f"  Mode:              {mode_label}")
    print(f"  Scope:             {scope_label}")
    print(f"  Threshold:         {threshold}")
    print(f"  Topic Name Weight: {topic_name_weight}")
    print(f"  Top N Matches:     {top_n}")
    print(f"{'='*60}\n")

    conn = sqlite3.connect(config.DATABASE_FILE)
    cursor = conn.cursor()

    categories, vectorizer, category_vectors = setup_categorization_engine()

    if include_already_categorized:
        sql_query = """
            SELECT
                t.label_id,
                t.label_name,
                f.factor_text,
                t.category
            FROM
                Property_Factor_Labels t
            JOIN
                Property_Factors f ON t.label_id = f.label_id
        """
    else:
        sql_query = """
            SELECT
                t.label_id,
                t.label_name,
                f.factor_text,
                t.category
            FROM
                Property_Factor_Labels t
            JOIN
                Property_Factors f ON t.label_id = f.label_id
            WHERE
                t.category IS NULL OR t.category = ''
        """

    try:
        cursor.execute(sql_query)
        topics = cursor.fetchall()
    except sqlite3.OperationalError as e:
        print(f"Database error: {e}")
        conn.close()
        return

    if not topics:
        print("No topics found matching the scope. Nothing to do.")
        conn.close()
        return

    print(f"Found {len(topics)} topics to evaluate.\n")

    categorized_results = []
    uncategorized_results = []
    recategorized_results = []

    for topic_id, topic_name, factor_text, existing_category in topics:

        topic_vector = _build_topic_vector(vectorizer, topic_name, factor_text, topic_name_weight)
        scores = cosine_similarity(topic_vector, category_vectors)

        max_score = scores.max()
        best_match_index = scores.argmax()

        top_indices = scores[0].argsort()[::-1][:top_n]
        top_matches = [(categories[i], scores[0, i]) for i in top_indices]

        if max_score > threshold:
            found_category = categories[best_match_index]
            changed = existing_category and existing_category != found_category

            entry = {
                "id": topic_id,
                "name": topic_name,
                "new_category": found_category,
                "old_category": existing_category or "(none)",
                "score": max_score,
                "top_matches": top_matches,
            }

            if changed:
                recategorized_results.append(entry)
            else:
                categorized_results.append(entry)

            if not dry_run:
                cursor.execute(
                    "UPDATE Property_Factor_Labels SET category = ? WHERE label_id = ?",
                    (found_category, topic_id)
                )
        else:
            uncategorized_results.append({
                "id": topic_id,
                "name": topic_name,
                "old_category": existing_category or "(none)",
                "score": max_score,
                "top_matches": top_matches,
            })

    if not dry_run:
        conn.commit()
    conn.close()
    """
    if categorized_results:
        print(f"--- CATEGORIZED ({len(categorized_results)}) ---")
        for r in sorted(categorized_results, key=lambda x: x["score"], reverse=True):
            print(f"  '{r['name']}' -> {r['new_category']}  (score: {r['score']:.3f})")
            for cat, sc in r["top_matches"]:
                print(f"       {cat}: {sc:.3f}")
            print()
    """

    if recategorized_results:
        print(f"--- WOULD RECATEGORIZE ({len(recategorized_results)}) ---")
        for r in sorted(recategorized_results, key=lambda x: x["score"], reverse=True):
            print(f"  '{r['name']}' : {r['old_category']} -> {r['new_category']}  (score: {r['score']:.3f})")
            for cat, sc in r["top_matches"]:
                print(f"       {cat}: {sc:.3f}")
            print()

    if uncategorized_results:
        print(f"--- BELOW THRESHOLD ({len(uncategorized_results)}) ---")
        for r in sorted(uncategorized_results, key=lambda x: x["score"], reverse=True):
            print(f"  '{r['name']}' stuck at {r['old_category']}  (best score: {r['score']:.3f})")
            for cat, sc in r["top_matches"]:
                print(f"       {cat}: {sc:.3f}")
            print()

    total = len(categorized_results) + len(recategorized_results) + len(uncategorized_results)
    print(f"{'='*60}")
    print(f"  SUMMARY")
    print(f"  Total evaluated:    {total}")
    print(f"  Categorized:        {len(categorized_results)}")
    print(f"  Recategorized:      {len(recategorized_results)}")
    print(f"  Below threshold:    {len(uncategorized_results)}")
    if dry_run:
        print(f"\n  ** No changes written. Set dry_run=False to commit. **")
    else:
        print(f"\n  ** Changes committed to database. **")
    print(f"{'='*60}")


# =============================================================================
#  RUN — reads from CONFIGURATION block above, no need to edit here
# =============================================================================

if __name__ == '__main__':
    if RUN_MODE == "interactive":
        interactive_categorize(
            threshold=THRESHOLD,
            topic_name_weight=TOPIC_NAME_WEIGHT,
            include_already_categorized=INCLUDE_ALREADY_CATEGORIZED,
            dry_run=DRY_RUN,
            top_n=SHOW_TOP_N_MATCHES,
        )
    else:
        categorize_topics(
            threshold=THRESHOLD,
            topic_name_weight=TOPIC_NAME_WEIGHT,
        )
