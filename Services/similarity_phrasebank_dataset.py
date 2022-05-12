from collections import defaultdict
import datetime
import json
import os
import time
from mongo_handler import MongoHandler
from sentence_transformers import SentenceTransformer, util
import torch


def get_all_original_samples(
    path_to_input_txt="Services/data/financial_phrasebank/Sentences_50Agree.txt",
    output_dir=None,
    val_split_percentage=0.2,
):
    list_of_all_samples = []
    list_of_dicts_train_to_save = []
    list_of_dicts_val_to_save = []
    with open(path_to_input_txt, "r") as f:
        list_of_lines = f.readlines()
    for idx, line in enumerate(list_of_lines):
        text, label = line.split("@")
        if label.strip() == "neutral":
            continue
        
        # if label.strip() == "negative":
        #     print(idx)
        list_of_all_samples.append({"text": text.strip(), "label": label.strip()})

    # random.shuffle(list_of_all_samples)
    # num_of_val_samples = int(len(list_of_all_samples) * val_split_percentage)
    # list_of_dicts_val_to_save = list_of_all_samples[:num_of_val_samples]
    # list_of_dicts_train_to_save = list_of_all_samples[num_of_val_samples:]

    return list_of_all_samples


def get_sentences_from_corpus():
    mongo_handler_obj = MongoHandler()
    mongo_handler_obj.connect_to_mongo()
    db = mongo_handler_obj.get_database()
    data = db["input_data"].find({"is_used": True})

    list_of_sentences = []
    for item in data:
        list_of_sentences += item["mda_sentences"]

    return list(set(list_of_sentences))


def logic(top_k=3):
    list_of_phrasebank_samples = get_all_original_samples()
    list_of_sentences_corpus = get_sentences_from_corpus()
    embedder = SentenceTransformer("all-MiniLM-L6-v2", device="cuda")
    print("Phrasebank len:", len(list_of_phrasebank_samples))
    print("Corpus len:", len(list_of_sentences_corpus))
    # Make embeddings for phrasebank and corpus
    start_time = datetime.datetime.now()
    query_embedding = embedder.encode(
        list_of_phrasebank_samples,
        convert_to_tensor=True,
        device="cuda",
        show_progress_bar=True,
    )
    corpus_embeddings = embedder.encode(
        list_of_sentences_corpus,
        convert_to_tensor=True,
        device="cuda",
        show_progress_bar=True,
    )
    end_time = datetime.datetime.now()

    hits = util.semantic_search(query_embedding, corpus_embeddings, top_k=top_k)

    dict_of_res = defaultdict(list)
    for idx, hits_per_query in enumerate(hits):
        for hit in hits_per_query:
            dict_of_res[idx].append(
                (list_of_sentences_corpus[hit["corpus_id"]], hit["score"])
            )

        if idx % 100 == 0:
            print(idx, "out of", len(hits))

    with open("mapped_phrasebank_to_corpus.json", "w") as f:
        json.dump(dict_of_res, f)


def extract_relevant_samples_by_hand(path_to_mapped_json, path_to_processed_till_now):
    if not os.path.exists(path_to_processed_till_now):
        dict_of_processed_till_now = defaultdict(dict)
    else:
        with open(path_to_processed_till_now, "r") as f:
            dict_of_processed_till_now = json.load(f)
        dict_of_processed_till_now = defaultdict(dict, dict_of_processed_till_now)

    list_of_phrasebank_samples = get_all_original_samples()
    with open(path_to_mapped_json, "r") as f:
        dict_of_res = json.load(f)

    list_of_keys = [int(k) for k in list(dict_of_processed_till_now.keys())]
    last_processed_idx = sorted(list_of_keys)[-1]
    
    for idx, item in enumerate(list_of_phrasebank_samples):
        idx = str(idx)
        if int(idx) <= last_processed_idx:
            continue
        
        
        print(f"----------{idx}/{len(list_of_phrasebank_samples)}--------------")
        print(item["text"])
        print(f"-----------{item['label'].upper()}---------------")
        user_input = input("Relevant (y/n/m): ")

        while user_input.lower() not in ["n", "y", "m"]:
            user_input= input("Provide valid input (y/n/m): ")
        
        if user_input.lower() == "n":
            continue

        elif user_input.lower() == "y" or user_input.lower() == "m":
            dict_of_processed_till_now[idx]["original"] = item["text"]
            dict_of_processed_till_now[idx]["original_label"] = item["label"]
            dict_of_processed_till_now[idx]["original_keep"] = user_input
            for sim_idx, similars in enumerate(dict_of_res[idx]):
                print("---------Original sentence------------\n")
                print(item['text'] + '\n')
                print(f"---------Similar sentence: score {similars[1]}------------\n")
                print(similars[0] + '\n')
                print(f"--------{item['label'].upper()}-----------")
                user_input = input(f"Relevant similar {sim_idx} (y/n/m): ")
                while user_input.lower() not in ["n", "y", "m"]:
                    user_input= input("Provide valid input (y/n/m): ")
                
                
                dict_of_processed_till_now[idx][f"similar_{sim_idx}"] = (
                    similars[0],
                    similars[1],
                    user_input.lower(),
                )

            with open(path_to_processed_till_now, "w") as f:
                json.dump(dict_of_processed_till_now, f)


extract_relevant_samples_by_hand(
    "Services/data/adapter_dataset/mapped_phrasebank_to_corpus.json",
    "Services/data/adapter_dataset/extracted_manualy.json",
)