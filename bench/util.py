
def cut_by(l, fraction):
    # there is a O(1) algorithm to do that, I don't care though :)
    l = l[:]
    l.sort()
    return l[int(len(l) * fraction)] * 1000

def print_results(all_items, total_time):
    print "Average throuhput: %dmsgs/s" % (len(all_items) / total_time)
    latency_95 = cut_by(all_items, 0.95)
    latency_99 = cut_by(all_items, 0.99)
    print ("Average latency: %.1fms 95%% latency: %.1fms, 99%% latency: %.1fms" % 
           ((sum(all_items) / len(all_items) * 1000), latency_95, latency_99))
