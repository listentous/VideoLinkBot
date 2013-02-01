"""
Would be cool if posted links were sorted in order by score achieved by their parent comment.
--> would require some re-processing of already-scraped comments when updating a post.

Also: should periodically keep tabs on the scores of posts submitted by the bot.
Could then identify subreddits where the bot is clearly not appreciated and black list those 
subreddits to ensure the bot doesn't post where it's not wanted. This would be a separate scraper.

Should consider blacklisting IAMA and AskReddit just cause they get sooooo many comments.
Should also consider just not posting when a submission has already achieved a certain 
threshhold number of comments and the link_id doesn't appear in botCommentsMemo.

Need to implement some kind of house-keeping function to clear out old entries from the memos,
otherwise they'll just needlessly leech RAM. botCommentsMemo we can leave alone, but should
periodically flush old entries from the other two memos.

If rescraping a post and no new links found, shouldn't edit comment.
"""

import praw
from praw.errors import APIException
import re
import urlparse as up
from urllib2 import Request, urlopen
import time

try:
    from BeautifulSoup import BeautifulSoup
except:
    from bs4 import BeautifulSoup

_ua = "YoutubeLinkBot reddit bot by /u/shaggorama"
r = praw.Reddit(_ua)

botCommentsMemo = {}
scrapedCommentsMemo = {}
scrapedLinksMemo = {}

def login(fname='loginCredentials.txt', _user=None, _pass=None):
    if _user is None and _pass is None:
        with open(fname,'r') as f:
            _user = f.readline().strip()
            _pass = f.readline().strip()
    print "Logging in as: {0} / {1}".format(_user, _pass)
    r.login(username=_user, password=_pass)

def get_video_links_from_html(text):
    """
    Strips video link from a string in html format
    by looking for the href attribute.
    """
    # could also just use BeautifulSoup, but this regex works fine
    link_pat   = re.compile('href="(.*?)"') 
    #pat_domain = re.compile('http://([^/]*?)/')
    #links
    links = link_pat.findall(text)
    yt_links = []
    for l in links:
        parsed = up.urlparse(l)
        #parsed.netloc.lower() #not really necessary
        for elem in parsed.netloc.split('.'):
            if elem in ('youtube','youtu','ytimg'):
                yt_links.append(l)
                break
    return yt_links

def get_title(url):
    """
    returns the title of a webpage given a url
    (e.g. the title of a youtube video)
    """
    def _get_title(_url):
        request  = Request(_url)
        response = urlopen(request)
        data     = response.read()
        soup = BeautifulSoup(data)
        title = soup.title.string[:-10] # strip out " - YouTube"
        title = title.replace('|','')
        title = title.replace('*','')
        return title
    try:
        title = _get_title(url)
    except Exception, e:
        # I think youtube might be blocking me here. Let's try slowing it down.
        print "Encountered some error getting title for video at", url
        print e
        time.sleep(2) # hopefully this isn't too massive of a slowdown. we'll enouncter this exception everytime we hit youtube.googleapis.com
        try:
            title = _get_title(url)
        except:
            print 'OK then, let''s just call it "..."'
            title = '...(trouble getting video title)...' # Passing in None makes the link completely inaccessible.
    return title

def scrape(submission):
    """
    Given a submission id, scrapes that submission and returns a list of comments
    associated with their links
    
    @submission: a 
    """        
    ### Should add in some functionality for recognizing when we've already maxed-out the comment length on a post.
    ### OH SHIT! better yet, figure out a way to RESPOND TO MY OWN COMMENT WITH ADDITIONAL LINKS.
    # just for convenience
    if type(submission) == type(''):
        submission = r.get_submission(submission_id = submission)
    # for updating links and whatever.
    if scrapedLinksMemo.has_key(submission.id):
        print "We've scraped this post before. Getting our comment to update."
        collected_links = scrapedLinksMemo[submission.id]
        #scrapedCommentIDs = get_scraped_comments(submission.id) # ignore comments we've already scraped for speed. Doubt it will add much. Right now, I'm doing this wrong.
        scrapedCommentIDs = scrapedCommentsMemo[submission.id]
        print "We have already collected %d video links on this submission." % len(collected_links)
    else:
        print "This post has not been scraped (recently)."
        collected_links   = {}
        scrapedCommentIDs = set()
        scrapedLinksMemo[submission.id]    = collected_links
        scrapedCommentsMemo[submission.id] = scrapedCommentIDs 
    print "got %d comments" % len(submission.all_comments_flat)
    for i, comment in enumerate(submission.all_comments_flat):
        if i%10 == 0:
            print "Scraped %d comments." % i
        if comment.id in scrapedCommentIDs:
            continue
        try:
            if comment.author.name == r.user.name: # deleted comment handling doesn't seem to be working properly.
                # if we have already memoized a bot comment for this post, continue
                # otheriwse, confirm found bot comment contains links and if it does, 
                # memoize it.
                if botCommentsMemo.has_key(submission.id):
                    continue
                elif get_video_links_from_html(comment.body_html):
                    botCommentsMemo[submission.id] = comment
                    print "recognized bot comment"
            else:
                links = get_video_links_from_html(comment.body_html)
                for link in links:
                    add_memo_entry(comment, link)
        except Exception, e:
            # ignore deleted comments and comments by deleted users.
            print "encountered some error in scrape()"
            print e
            continue # why do name attribute errors keep getting re-raised???
        scrapedCommentIDs.add(comment.id)
    print "Scraped {0} comments, found {1} links".format(i, len(collected_links) )
    return collected_links  # this isn't really even necessary since we could just call it down from the memo.

def get_scraped_comments(link_id):
    """ to be retired in favor of call to memo"""
    print "building comments memo"
    if scrapedLinksMemo.has_key(link_id):
        collected_links = scrapedCommentsMemo[link_id]
        scraped = set( [collected_links[url]['id'] for url in collected_links] )
    else:
        "Populating scrapedCommentsMemo with", link_id
        scraped = set()
        scrapedCommentsMemo[link_id] = {} 
    return  scraped
    
def add_memo_entry(comment, link):
    submission_id = comment.submission.id
    if not link:
        if not scrapedCommentsMemo.has_key(submission_id):
            scrapedCommentsMemo[submission_id] = set()      # this might be redundant
        scrapedCommentsMemo[submission_id].add(comment.id)
    try:
        username = comment.author.name
    except:
        username = None
    link_entry = {'author':username, 'created_utc':comment.created_utc, 'permalink':comment.permalink, 'id':comment.id}
    if scrapedLinksMemo.has_key(submission_id):
        collected_links = scrapedLinksMemo[submission_id]        
        try:
            if collected_links[link]['created_utc'] < comment.created_utc:
                collected_links[link] = link_entry                            
        except KeyError:
            collected_links[link] = link_entry
            #scrapedCommentIDs.append(scrapedCommentIDs) # would probably be easier to just just use a set   
    else:
        scrapedLinksMemo[submission_id][link] = link_entry

def build_comment(collected_links):
    text = '''Here are the collected video links posted in response to this post (deduplicated to the best of my ability):

|Source Comment|Video Link|
|:-------|:-------|\n'''    
    
    video_urls = [k for k in collected_links]
    authors = [collected_links[url]['author'] for url in video_urls]
    permalinks = [collected_links[url]['permalink'] for url in video_urls]
    titles = [get_title(url) for url in video_urls]    
    
    # pass comments to formatter as a list of dicts
    for link in [ {'author':a, 'permalink':p, 'title':t, 'url':u} for a,p,t,u in zip(authors, permalinks, titles, video_urls)]:
        #formatted_text+='|[{author}]({permalink}) | [{title}]({url})|'.format(link)
        text+= u'| [%(author)s](%(permalink)s) | [%(title)s](%(url)s) |\n' % link        
    text = trim_comment(text) # why not be proactive.
    return text

    
def post_comment(link_id, subm, text):
    try:
        if botCommentsMemo.has_key(link_id):
            bot_comment = botCommentsMemo[link_id]
            bot_comment.edit(text)
        else:
            bot_comment = subm.add_comment(text)
            botCommentsMemo[link_id] = bot_comment
        result = True
    except APIException, e:
        # need to handle comments that are too long. 
        # Really, this should probably be in build_comment()
        print e
        print "sleeping for 5 seconds, trimming comment"
        time.sleep(5)       # maybe the API is annoyed with
        trim_comment(text)  # maybe the comment is too long (this should have been handled already)
        #post_comment(link_id, subm, text)
        result = False 
    return result
    
def trim_comment(text, targetsize=10000):
    """
    If comment is longer than 10000 chars, reddit won't let us post it. This boils down to around 50 links (I think).
    """
    # Removing permalink's to comments would significantly reduce the size of my comments.
    # could still post a link to the user's commenting history
    # Alternatively, could post a shortlink (?)
    print "Trimming comment down to %d chars." % targetsize
    while len(text)> targetsize:
        text = '\n'.join(text.split('\n')[:-1])#[2:]
    print "Processed comment length:",len(text)
    return text
    
def post_aggregate_links(link_id='178ki0', max_num_comments = 1000, min_num_comments = 8):   
    """Not sure which function to call? You probably want this one."""    
    subm = r.get_submission(submission_id = link_id)      
    if not min_num_comments < subm.num_comments < max_num_comments:
        print "[NO POST] Submission has %d comments. Not worth scraping." % subm.num_comments
        return None
    try:
        print u'Scraping "{0}"'.format(subm.title)
    except:
        print u'Scraping "{0}"'.format(subm.id)
    links = scrape(subm) # Theoretically, we could just pull this down from the memo.    
    #if text[-5:] == '----|':
    #    print 'No links to post'    
    n_links = len(links)
    if  n_links >2:
        authors = set([links[url]['author'] for url in links])
        if len(authors) >1:
            try:
                print u'[POST] Posting {nlinks} links to "{sub}" post "{post}"'.\
                    format(nlinks = n_links
                          ,sub    = subm.subreddit.display_name
                          ,post   = subm.title)
            except:
                print u'[POST] Posting {nlinks} links to "{sub}" post "{post}"'.\
                    format(nlinks = n_links
                          ,sub    = subm.subreddit.id
                          ,post   = subm.id)
            text = build_comment(links)
            posted = False
            while not posted:
                posted = post_comment(link_id, subm, text)
            print "Video links successfully posted."
        else:
            print "[NO POST] All links from same user. Need at least 2 different users to post."
    else: 
        print "[NO POST] Only found %d links. Need 3 to post." % n_links

if __name__ == '__main__':
    login()
    post_aggregate_links()
    